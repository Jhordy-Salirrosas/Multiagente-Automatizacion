"""
BaseAgent — Wrapper estandarizado sobre el LLM usando LangChain LCEL.

Usa ChatOpenAI (compatible con GitHub Models, OpenAI, cualquier endpoint
OpenAI-compatible) + ChatPromptTemplate + StrOutputParser como cadena LCEL.

Decisiones de diseño:
  - **LangChain LCEL**: prompt | llm | parser como cadena composable.
  - **Stateless por llamada**: cada `run()` envía SOLO el system_prompt + el
    prompt del turno actual. NO acumula historial entre invocaciones.
  - **Retry con backoff exponencial** en rate limits (HTTP 429).
  - **Fallback automático a modo mock** si el retry final falla, para que la
    demo NUNCA se rompa frente al jurado.
  - **Tracing con LangSmith**: las cadenas LCEL se trazan automáticamente
    cuando LANGSMITH_TRACING=true.
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
from config import EXECUTION_MODE, LLM_API_KEY, get_langchain_llm

# LangSmith tracing (§5.3): decorador @traceable para observabilidad.
# Si langsmith no está instalado, usamos un decorador no-op.
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast

F = TypeVar('F', bound=Callable[..., Any])

if TYPE_CHECKING:
    def traceable(*args: Any, **kwargs: Any) -> Callable[[F], F]:
        def decorator(func: F) -> F: return func
        return decorator
else:
    try:
        from langsmith import traceable  # type: ignore
    except ImportError:
        def traceable(*args: Any, **kwargs: Any) -> Callable[[F], F]:
            def decorator(func: F) -> F: return func
            if args and callable(args[0]):
                return cast(Callable[[F], F], lambda f: f)(args[0])
            return decorator


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
      - "real": usa LangChain LCEL → ChatOpenAI → LLM real
      - "mock": usa _default_mock_response() (override en subclases)
    """

    MAX_RETRIES = 3
    INITIAL_BACKOFF_SECONDS = 2.0

    def __init__(
        self,
        agent_name: AgentName,
        system_prompt: str,
        model_name: str | None = None,
        max_loops: int = 1,
        mock_response: Optional[str] = None,
    ):
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.mock_response = mock_response
        self._chain = None
        self._rate_limited_until: float = 0.0
        self._initialize()

    def _initialize(self) -> None:
        """Inicializa la cadena LangChain LCEL si estamos en modo real."""
        if EXECUTION_MODE != "real":
            print(f"ℹ️  {self.agent_name.value}: modo MOCK (sin LLM)")
            return
        if not LLM_API_KEY:
            print(f"[WARN]  {self.agent_name.value}: LLM_API_KEY vacío, cayendo a MOCK")
            return
        try:
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import StrOutputParser

            llm = get_langchain_llm(temperature=0.3, max_tokens=1024)
            if llm is None:
                print(f"[WARN]  {self.agent_name.value}: no se pudo crear LLM, cayendo a MOCK")
                return

            # ► Cadena LCEL: prompt → llm → parser
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", self.system_prompt),
                ("human", "{prompt}"),
            ])
            self._chain = prompt_template | llm | StrOutputParser()
            print(f"✅ {self.agent_name.value}: inicializado con LangChain LCEL")

        except ImportError as e:
            print(f"[WARN]  {self.agent_name.value}: falta dependencia LangChain: {e}")
            self._chain = None
        except Exception as e:
            print(f"[WARN]  {self.agent_name.value}: no se pudo inicializar: {type(e).__name__}: {e}")
            self._chain = None

    # =========================================================================
    # Ejecución principal
    # =========================================================================
    @traceable(name="BaseAgent.run")
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

        if self._chain is None:
            return self._safe_mock(prompt, reason="no_llm_initialized")

        last_error: Optional[Exception] = None
        for attempt in range(self.MAX_RETRIES):
            try:
                # ► Invocación LCEL: output limpio sin ruido de timestamps
                output = self._chain.invoke({"prompt": prompt})
                if not isinstance(output, str):
                    output = str(output)
                return output
            except Exception as e:
                last_error = e
                err_msg = str(e)
                if any(sig in err_msg for sig in _RETRYABLE_ERROR_SIGNATURES):
                    wait = self.INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                    print(f"[WARN]  {self.agent_name.value}: rate limit, "
                          f"reintento {attempt+1}/{self.MAX_RETRIES} en {wait:.1f}s...")
                    time.sleep(wait)
                    continue
                print(f"[WARN]  {self.agent_name.value}: error no recuperable: {type(e).__name__}: {str(e)[:200]}")
                break

        self._rate_limited_until = time.time() + 60.0
        print(f"[WARN]  {self.agent_name.value}: cae a modo mock por 60s")
        return self._safe_mock(prompt, reason="all_retries_failed")

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
          - JSON dentro de output ruidoso (el JSON real está al final).

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
        Con LangChain LCEL, el output ya es limpio (sin timestamps de Swarms).
        Se mantiene el método por compatibilidad con subclases que lo llaman,
        pero ahora simplemente retorna el texto limpio.
        """
        if not text:
            return ""
        return text.strip()

    def emit_event(self, event_name: str, **data: Any) -> None:
        """Publica un evento en el event bus."""
        event_bus.emit(source=self.agent_name, event_name=event_name, **data)
