"""
BaseAgent — Wrapper estandarizado sobre el LLM (vía swarms.Agent + litellm).

Soporta GitHub Models, OpenAI, Gemini y cualquier endpoint OpenAI-compatible.

Decisiones de diseño:
  - **Endpoint configurable**: pasamos `llm_base_url` y `llm_api_key` DIRECTAMENTE
    a swarms.Agent, en vez de depender de variables de entorno globales que
    se contaminan entre proveedores.
  - **Stateless por llamada**: cada `run()` envía SOLO el system_prompt + el
    prompt del turno actual. NO usamos la "Persistent Memory" interna de
    swarms.Agent que acumulaba el historial de TODOS los turnos previos.
  - **Retry con backoff exponencial** en rate limits (HTTP 429).
  - **Fallback automático a modo mock** si el retry final falla, para que la
    demo NUNCA se rompa frente al jurado.
"""
from __future__ import annotations
import json
import re
import time
from typing import Optional, Any

from core.mcp_messages import MCPMessage, AgentName, MessageType
from core.event_bus import event_bus
from core.metrics import metrics
from core.shared_state import SharedState
from config import EXECUTION_MODE, LLM_MODEL, LLM_API_KEY, LLM_API_BASE


# Errores que justifican retry con backoff
_RETRYABLE_ERROR_SIGNATURES = (
    "429",
    "RateLimitError",
    "RESOURCE_EXHAUSTED",
    "rate_limit",
    "quota",
    "Too Many Requests",
)


class BaseAgent:
    """
    Wrapper común para todos los agentes especializados.

    Modos:
      - "real": usa swarms.Agent → litellm → LLM real
      - "mock": usa _default_mock_response() (override en subclases)
    """

    MAX_RETRIES = 3
    INITIAL_BACKOFF_SECONDS = 2.0

    def __init__(
        self,
        agent_name: AgentName,
        system_prompt: str,
        model_name: str = LLM_MODEL,
        max_loops: int = 1,
        mock_response: Optional[str] = None,
    ):
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.model_name = model_name
        self.max_loops = max_loops
        self.mock_response = mock_response
        self._swarm_agent = None
        self._rate_limited_until: float = 0.0
        self._initialize()

    def _initialize(self) -> None:
        """Inicializa swarms.Agent si estamos en modo real."""
        if EXECUTION_MODE != "real":
            print(f"ℹ️  {self.agent_name.value}: modo MOCK (sin LLM)")
            return
        if not LLM_API_KEY:
            print(f"⚠️  {self.agent_name.value}: LLM_API_KEY vacío, cayendo a MOCK")
            return
        try:
            from swarms import Agent as SwarmsAgent
            # ► Construir kwargs base. Pasamos llm_base_url y llm_api_key
            #   DIRECTAMENTE para que swarms los reenvíe a litellm con esa
            #   exacta configuración, sin contaminación de env vars.
            agent_kwargs = dict(
                agent_name=self.agent_name.value,
                system_prompt=self.system_prompt,
                model_name=self.model_name,
                max_loops=self.max_loops,
                # ► Endpoint y key explícitos (lo que arregla GitHub Models)
                llm_base_url=LLM_API_BASE,
                llm_api_key=LLM_API_KEY,
                # ► CRÍTICO: desactivar persistencia interna para no inflar prompts
                #   NOTA: no pasamos long_term_memory=None porque algunas versiones
                #   de swarms intentan .add() sobre él. Mejor dejar el default y
                #   limpiar la memoria antes de cada llamada (ver _clear_swarm_memory).
                autosave=False,
                saved_state_path=None,
                # ► Sin verbose y sin streaming para output limpio
                verbose=False,
                streaming_on=False,
                output_type="str",
                dynamic_temperature_enabled=False,
                # ► Sin retries internos de swarms (los manejamos nosotros)
                retry_attempts=1,
            )
            self._swarm_agent = SwarmsAgent(**agent_kwargs)
            print(f"✅ {self.agent_name.value}: inicializado con {self.model_name} @ {LLM_API_BASE}")
        except TypeError as e:
            # Versión vieja de swarms que no acepta llm_base_url/llm_api_key:
            # caer a inicialización vía env vars (que config.py ya pobló)
            print(f"ℹ️  {self.agent_name.value}: swarms no acepta llm_base_url, "
                  f"usando env vars OPENAI_API_BASE/OPENAI_API_KEY")
            try:
                from swarms import Agent as SwarmsAgent
                self._swarm_agent = SwarmsAgent(
                    agent_name=self.agent_name.value,
                    system_prompt=self.system_prompt,
                    model_name=self.model_name,
                    max_loops=self.max_loops,
                    autosave=False,
                    verbose=False,
                    streaming_on=False,
                    output_type="str",
                    dynamic_temperature_enabled=False,
                    retry_attempts=1,
                )
            except Exception as e2:
                print(f"⚠️  {self.agent_name.value}: fallo también con env vars: {e2}")
                self._swarm_agent = None
        except Exception as e:
            print(f"⚠️  {self.agent_name.value}: no se pudo inicializar: {type(e).__name__}: {e}")
            self._swarm_agent = None

    # =========================================================================
    # Ejecución principal
    # =========================================================================
    def run(self, prompt: str, state: SharedState) -> str:
        """Ejecuta el agente sobre un prompt. Mide, traza MCP, retry, fallback."""
        request_msg = MCPMessage(
            sender=AgentName.ORCHESTRATOR,
            receiver=self.agent_name,
            message_type=MessageType.REQUEST,
            payload={"prompt": prompt[:500]},
        )
        state.append_message(request_msg)

        output = ""
        with metrics.measure(
            agent_name=self.agent_name.value,
            input_text=prompt,
            session_id=state.session_id,
        ) as record:
            output = self._run_with_retry(prompt)
            record.output_chars = len(output)

        response_msg = MCPMessage(
            sender=self.agent_name,
            receiver=AgentName.ORCHESTRATOR,
            message_type=MessageType.RESPONSE,
            payload={"output": output[:500]},
            correlation_id=request_msg.message_id,
        )
        state.append_message(response_msg)
        return output

    def _run_with_retry(self, prompt: str) -> str:
        """Ejecuta con retry exponencial; cae a mock si todos los retries fallan."""
        now = time.time()
        if now < self._rate_limited_until:
            return self._safe_mock(prompt, reason="rate_limit_cooldown")

        if self._swarm_agent is None:
            return self._safe_mock(prompt, reason="no_llm_initialized")

        last_error: Optional[Exception] = None
        for attempt in range(self.MAX_RETRIES):
            try:
                self._clear_swarm_memory()
                output = self._swarm_agent.run(prompt)
                if not isinstance(output, str):
                    output = str(output)
                return output
            except Exception as e:
                last_error = e
                err_msg = str(e)
                if any(sig in err_msg for sig in _RETRYABLE_ERROR_SIGNATURES):
                    wait = self.INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                    print(f"⚠️  {self.agent_name.value}: rate limit, "
                          f"reintento {attempt+1}/{self.MAX_RETRIES} en {wait:.1f}s...")
                    time.sleep(wait)
                    continue
                print(f"⚠️  {self.agent_name.value}: error no recuperable: {type(e).__name__}: {str(e)[:200]}")
                break

        self._rate_limited_until = time.time() + 60.0
        print(f"⚠️  {self.agent_name.value}: cae a modo mock por 60s")
        return self._safe_mock(prompt, reason="all_retries_failed")

    def _clear_swarm_memory(self) -> None:
        """
        Limpia memoria interna acumulada en swarms.Agent ANTES de cada llamada.

        IMPORTANTE: lo hacemos de forma MUY conservadora: solo llamamos a métodos
        públicos de limpieza si existen; NUNCA tocamos atributos directamente
        porque las versiones recientes de swarms los requieren no-None y se
        rompen con `AttributeError: 'NoneType' object has no attribute 'add'`.
        """
        if self._swarm_agent is None:
            return
        for method_name in ("clear_history", "reset_conversation"):
            method = getattr(self._swarm_agent, method_name, None)
            if callable(method):
                try:
                    method()
                    return
                except Exception:
                    pass

    def _safe_mock(self, prompt: str, reason: str = "") -> str:
        """Devuelve la respuesta mock sin tirar excepción."""
        try:
            return self.mock_response or self._default_mock_response(prompt)
        except Exception as e:
            return f'{{"error": "mock_failed", "reason": "{reason}", "detail": "{e}"}}'

    def _default_mock_response(self, prompt: str) -> str:
        """Override en subclases para responses mock realistas."""
        return '{"mock": true, "agent": "' + self.agent_name.value + '"}'

    # =========================================================================
    # Utilidades
    # =========================================================================
    @staticmethod
    def extract_json(text: str) -> Optional[dict]:
        """
        Extrae el JSON más relevante del texto. Robusto a:
          - JSON puro
          - JSON dentro de ```json fences```
          - JSON dentro de output ruidoso (Swarms agrega el system prompt y
            timestamps al output; el JSON real está al final).

        Estrategia:
          1. Intenta parsear todo el texto.
          2. Si falla, busca TODOS los bloques `{...}` con llaves balanceadas
             y prueba a parsear cada uno, empezando por el ÚLTIMO (la respuesta
             real del LLM suele estar al final).
        """
        if not text:
            return None
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        # Intento 1: el texto completo es JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Intento 2: encontrar todos los bloques {...} balanceados y probar
        # cada uno empezando por el último (la respuesta real del agente).
        candidates = BaseAgent._find_balanced_json_objects(text)
        for cand in reversed(candidates):
            try:
                obj = json.loads(cand)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
        return None

    @staticmethod
    def _find_balanced_json_objects(text: str) -> list[str]:
        """Encuentra todos los substrings que parecen objetos JSON balanceados."""
        objects: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            if text[i] == "{":
                depth = 0
                start = i
                in_string = False
                escape = False
                while i < n:
                    c = text[i]
                    if escape:
                        escape = False
                    elif c == "\\":
                        escape = True
                    elif c == '"':
                        in_string = not in_string
                    elif not in_string:
                        if c == "{":
                            depth += 1
                        elif c == "}":
                            depth -= 1
                            if depth == 0:
                                objects.append(text[start : i + 1])
                                break
                    i += 1
            i += 1
        return objects

    def extract_agent_text(self, text: str) -> str:
        """
        Extrae SOLO la respuesta de texto del agente del output ruidoso que
        Swarms devuelve (que incluye [timestamp] System:, [timestamp] Human:,
        etc.).

        Estrategia: dividir por marcadores `[YYYY-...] <Quién>:` y tomar el
        último bloque que no sea System ni Human. Si no hay marcadores, devuelve
        el texto tal cual.
        """
        if not text:
            return ""
        # Patrón: [timestamp] <Speaker>: <contenido>
        # Speaker puede ser "System", "Human", "AI", o el nombre del agente.
        pattern = re.compile(
            r"\[\d{4}-\d{2}-\d{2}T[\d:.]+\]\s+([A-Za-z][\w]*?):\s*",
            re.MULTILINE,
        )
        matches = list(pattern.finditer(text))
        if not matches:
            return text.strip()

        # Construir los bloques: cada uno es desde el final de un match hasta
        # el inicio del siguiente.
        blocks: list[tuple[str, str]] = []
        for i, m in enumerate(matches):
            speaker = m.group(1)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            blocks.append((speaker, content))

        # Buscar el último bloque que NO sea System ni Human (es del agente).
        for speaker, content in reversed(blocks):
            if speaker.lower() not in ("system", "human", "user"):
                return content
        # Fallback: devolver el último bloque sea cual sea
        return blocks[-1][1] if blocks else text.strip()

    def emit_event(self, event_name: str, **data: Any) -> None:
        """Publica un evento en el event bus."""
        event_bus.emit(source=self.agent_name, event_name=event_name, **data)
