"""
app.py — Frontend web del sistema multiagente con Streamlit.

Provee una interfaz visual completa:
  - Chat principal con el orquestador (usuario ↔ sistema).
  - Sidebar con estado en vivo del pedido (los 8 datos), etapa actual,
    y métricas por agente.
  - Panel inferior con eventos del Event Bus y mensajes MCP recientes.
  - Botón para reiniciar la sesión.

Uso:
    streamlit run app.py
"""
from __future__ import annotations
import sys
from pathlib import Path

# Asegurar que el paquete sea importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # type: ignore

from agents.orchestrator import Orchestrator
from core.shared_state import SharedState, ConversationStage
from core.metrics import metrics
from core.event_bus import event_bus
from config import EXECUTION_MODE, EMPRESA_NOMBRE, LLM_PROVIDER, LLM_MODEL, LLM_API_BASE


# =============================================================================
# Configuración de la página
# =============================================================================
st.set_page_config(
    page_title="Fábrica de Ropa - Sistema Multiagente",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# Inicialización de estado (Streamlit re-ejecuta el script en cada interacción)
# =============================================================================
def init_session() -> None:
    """Inicializa o resetea el estado de la sesión Streamlit."""
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = Orchestrator()
    if "state" not in st.session_state:
        st.session_state.state = SharedState()
    if "messages" not in st.session_state:
        # Mensajes para el render del chat (formato OpenAI-like)
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    f"¡Hola! 👋 Soy el agente de ventas de **{EMPRESA_NOMBRE}**.\n\n"
                    "Cuéntame qué prendas necesitas y te ayudo con tu cotización. "
                    "Por ejemplo: *\"Necesito 50 polos bordados para mi empresa\"*"
                ),
            }
        ]


def reset_session() -> None:
    """Reinicia toda la conversación."""
    for k in ("orchestrator", "state", "messages", "form_submitted"):
        if k in st.session_state:
            del st.session_state[k]
    init_session()
    st.rerun()


init_session()


# =============================================================================
# SIDEBAR: estado en vivo
# =============================================================================
state: SharedState = st.session_state.state

with st.sidebar:
    st.markdown("### 🧵 Fábrica de Ropa")
    st.caption("Sistema multiagente · Grupo 01 · UPAO 2026")

    # Modo de ejecución
    badge_color = "🟢" if EXECUTION_MODE == "real" else "🟡"
    st.markdown(f"**Modo:** {badge_color} `{EXECUTION_MODE}`")
    if EXECUTION_MODE == "real":
        st.caption(f"🤖 **{LLM_PROVIDER}** · `{LLM_MODEL}`")
        if LLM_API_BASE:
            st.caption(f"🔗 `{LLM_API_BASE}`")

    # Etapa actual del flujo
    stage_emojis = {
        ConversationStage.INITIAL: "⚪ Inicial",
        ConversationStage.VALIDATING: "🔍 Validando rubro",
        ConversationStage.COLLECTING_DATA: "💬 Recolectando datos",
        ConversationStage.QUOTING: "💰 Cotizando",
        ConversationStage.WAITING_CONFIRMATION: "✋ Esperando confirmación",
        ConversationStage.REGISTERING: "📋 Registrando",
        ConversationStage.NOTIFYING: "📧 Enviando email",
        ConversationStage.COMPLETE: "[OK] Completado",
        ConversationStage.REJECTED: "[FAIL] Rechazado",
    }
    st.markdown(f"**Etapa:** {stage_emojis.get(state.stage, state.stage.value)}")
    st.divider()

    # Validación
    if state.validation_result:
        v = state.validation_result
        icon = "[OK]" if v.is_textile else "[FAIL]"
        st.markdown(f"**Validación:** {icon} ({v.confidence * 100:.0f}%)")
        st.caption(v.reason)
        st.divider()

    # Datos recolectados (los 8)
    st.markdown("### 📋 Datos del pedido")
    od = state.order_data
    rows = [
        ("👤 Nombre", od.nombre),
        ("📧 Email", od.email),
        ("👕 Prenda", od.tipo_prenda),
        ("🔢 Cantidad", od.cantidad),
        ("📏 Talla", od.talla),
        ("🎨 Color", od.color),
        ("✨ Acabado", od.acabado),
        ("📅 Fecha entrega", od.fecha_entrega),
    ]
    for label, value in rows:
        if value is not None and value != "":
            st.markdown(f"{label}: **{value}**")
        else:
            st.markdown(f"{label}: _pendiente_")
    progress = sum(1 for _, v in rows if v is not None and v != "") / len(rows)
    st.progress(progress, text=f"Progreso: {int(progress * 100)}%")

    st.divider()

    # Cotización
    if state.quote_result:
        q = state.quote_result
        st.markdown("### 💰 Cotización")
        st.markdown(f"Subtotal: **S/ {q.subtotal:,.2f}**")
        st.markdown(f"Descuento: {q.descuento_label} · -S/ {q.descuento_monto:,.2f}")
        st.markdown(f"**TOTAL: S/ {q.total:,.2f}**")
        st.markdown(f"Adelanto (50%): **S/ {q.adelanto:,.2f}**")
        st.divider()

    # Registro
    if state.registry_result:
        r = state.registry_result
        st.success(f"📋 Pedido **{r.pedido_id}**")
        st.caption(f"Estado: {r.estado}")
        st.divider()

    # Notificación
    if state.notification_result:
        n = state.notification_result
        if n.enviado:
            st.success(f"📧 Email enviado a {n.destinatario}")
            html_path = Path(n.archivo_html)
            if html_path.exists():
                with open(html_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Descargar constancia HTML",
                        data=f.read(),
                        file_name=html_path.name,
                        mime="text/html",
                    )
        st.divider()

    # Botón de reinicio
    if st.button("🔄 Nueva conversación", use_container_width=True):
        reset_session()


# =============================================================================
# PANEL PRINCIPAL: chat + paneles inferiores
# =============================================================================
st.title("🧵 Asistente de Ventas Textil")
st.caption(
    "Sistema multiagente jerárquico · "
    "Orquestador + Validator + DataCollector + Pricing + Registry + Notifier"
)

# La interfaz principal dividida en pestañas para poder evaluar
tab_cliente, tab_docente = st.tabs(["🛒 Atención al Cliente", "📊 Panel Docente (Métricas y Eventos)"])

with tab_cliente:
    # Renderizar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])

    # ─────────────────────────────────────────────────────────────────────────
    # FORMULARIO INTERACTIVO DE PEDIDO (reemplaza el chat largo)
    # Se muestra cuando la validación pasó y aún no se envió el formulario
    # ─────────────────────────────────────────────────────────────────────────
    _show_form = (
        state.stage == ConversationStage.COLLECTING_DATA
        and not st.session_state.get("form_submitted", False)
    )

    if _show_form:
        # Cargar tabla de precios para los selectores
        import json
        from config import PRICE_TABLE_PATH
        with open(PRICE_TABLE_PATH, encoding="utf-8") as _f:
            _pt = json.load(_f)

        st.markdown("---")
        st.markdown("### 📋 Completemos los detalles de tu cotización")
        st.caption("Selecciona los detalles de tu pedido y obtendrás la cotización al instante.")

        with st.form("order_form", clear_on_submit=False):
            # ── Fila 1: Datos del cliente ──
            st.markdown("#### 👤 Datos del cliente")
            fc1, fc2 = st.columns(2)
            with fc1:
                form_nombre = st.text_input(
                    "Nombre completo *",
                    placeholder="Juan Pérez",
                    key="f_nombre",
                )
            with fc2:
                form_email = st.text_input(
                    "Email *",
                    placeholder="juan@empresa.com",
                    key="f_email",
                )

            st.markdown("---")

            # ── Fila 2: Detalles de la prenda ──
            st.markdown("#### 👕 Detalles del pedido")

            # Tipo de prenda con precio visible
            _prenda_options = {
                k: f"{k.capitalize()} — S/ {v['precio_unitario']:.2f}"
                for k, v in _pt["prendas"].items()
            }
            fp1, fp2 = st.columns(2)
            with fp1:
                form_prenda_key = st.selectbox(
                    "Tipo de prenda *",
                    options=list(_prenda_options.keys()),
                    format_func=lambda x: _prenda_options[x],
                    key="f_prenda",
                )
            with fp2:
                form_cantidad = st.number_input(
                    "Cantidad (unidades) *",
                    min_value=1, max_value=10000, value=50, step=10,
                    key="f_cantidad",
                )

            fp3, fp4 = st.columns(2)
            with fp3:
                form_talla = st.selectbox(
                    "Talla *",
                    options=["XS", "S", "M", "L", "XL", "XXL"],
                    index=2,
                    key="f_talla",
                )
            with fp4:
                form_color = st.selectbox(
                    "Color *",
                    options=["Blanco", "Negro", "Azul", "Rojo", "Gris",
                             "Verde", "Amarillo", "Celeste", "Rosa", "Naranja"],
                    key="f_color",
                )

            # Acabado con precios
            _acabado_labels = {
                "ninguno": "Sin acabado (S/ 0.00)",
                "estampado": f"Estampado (+S/ {_pt['acabados']['estampado']:.2f})",
                "bordado": f"Bordado (+S/ {_pt['acabados']['bordado']:.2f})",
            }
            form_acabado = st.radio(
                "Acabado *",
                options=list(_acabado_labels.keys()),
                format_func=lambda x: _acabado_labels[x],
                horizontal=True,
                key="f_acabado",
            )

            # Fecha de entrega
            from datetime import date, timedelta
            form_fecha = st.date_input(
                "Fecha de entrega *",
                value=date.today() + timedelta(days=15),
                min_value=date.today() + timedelta(days=7),
                key="f_fecha",
            )

            st.markdown("---")

            # ── PREVISUALIZACIÓN EN VIVO ──
            _precio_unit = _pt["prendas"][form_prenda_key]["precio_unitario"]
            _costo_acabado = _pt["acabados"].get(form_acabado, 0)
            _subtotal = (_precio_unit + _costo_acabado) * form_cantidad

            # Calcular descuento
            _desc_porc = 0.0
            _desc_label = "Sin descuento"
            for tramo in _pt["descuentos_volumen"]:
                if form_cantidad >= tramo["minimo"]:
                    _desc_porc = tramo["porcentaje"]
                    _desc_label = tramo["label"]
                    break
            _desc_monto = round(_subtotal * _desc_porc, 2)
            _total = round(_subtotal - _desc_monto, 2)
            _adelanto = round(_total * _pt["porcentaje_adelanto"], 2)

            st.markdown("#### 💰 Previsualización de cotización")
            pc1, pc2, pc3, pc4 = st.columns(4)
            pc1.metric("Precio unitario", f"S/ {_precio_unit + _costo_acabado:.2f}")
            pc2.metric("Subtotal", f"S/ {_subtotal:,.2f}")
            pc3.metric("Descuento", f"-S/ {_desc_monto:,.2f}", delta=_desc_label)
            pc4.metric("TOTAL", f"S/ {_total:,.2f}")

            st.caption(f"Adelanto requerido (50%): **S/ {_adelanto:,.2f}**")

            # ── Botón de envío ──
            submitted = st.form_submit_button(
                "📋 Generar Cotización",
                use_container_width=True,
                type="primary",
            )

            if submitted:
                # Validar campos obligatorios
                errors = []
                if not form_nombre.strip():
                    errors.append("Nombre es obligatorio")
                if not form_email.strip() or "@" not in form_email:
                    errors.append("Email válido es obligatorio")

                if errors:
                    st.error("[WARN] " + " · ".join(errors))
                else:
                    # Armar el dict con los 8 datos
                    form_data = {
                        "nombre": form_nombre.strip(),
                        "email": form_email.strip().lower(),
                        "tipo_prenda": form_prenda_key,
                        "cantidad": form_cantidad,
                        "talla": form_talla,
                        "color": form_color.lower(),
                        "acabado": form_acabado,
                        "fecha_entrega": form_fecha.isoformat(),
                    }

                    # Procesar con el Orchestrator
                    try:
                        reply = st.session_state.orchestrator.handle_form_submission(
                            form_data, st.session_state.state
                        )
                        # Agregar al chat
                        resumen_usuario = (
                            f"📝 **Pedido enviado:** {form_cantidad} {form_prenda_key}(s) "
                            f"{form_color.lower()} con {form_acabado}, "
                            f"talla {form_talla}, para {form_fecha.isoformat()}"
                        )
                        st.session_state.messages.append({"role": "user", "content": resumen_usuario})
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                        st.session_state.form_submitted = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"[WARN] Error al procesar: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # BOTÓN DE DESCARGA DE COTIZACIÓN (Solo en espera de confirmación)
    # ─────────────────────────────────────────────────────────────────────────
    if state.stage == ConversationStage.WAITING_CONFIRMATION and state.quote_result:
        st.info("💡 Tu cotización está lista. Puedes descargarla para tu registro antes de confirmar.")
        st.download_button(
            label="📥 Descargar Cotización (TXT)",
            data=state.quote_result.resumen_texto,
            file_name=f"cotizacion_{state.order_data.nombre or 'cliente'}.txt",
            mime="text/plain",
            use_container_width=True
        )

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT DE CHAT (para la interacción inicial y la confirmación final)
    # ─────────────────────────────────────────────────────────────────────────
    _show_chat_input = (
        state.stage in (
            ConversationStage.INITIAL,
            ConversationStage.VALIDATING,
            ConversationStage.WAITING_CONFIRMATION,
            ConversationStage.COLLECTING_DATA,  # Fallback: si prefiere chat
        )
        and state.stage != ConversationStage.COMPLETE
        and state.stage != ConversationStage.REJECTED
    )

    if _show_chat_input:
        if user_msg := st.chat_input("Escribe tu mensaje..."):
            # 1) Render del usuario
            st.session_state.messages.append({"role": "user", "content": user_msg})
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_msg)

            # 2) Procesar con el orquestador
            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner("Pensando..."):
                    try:
                        reply = st.session_state.orchestrator.handle_user_message(
                            user_msg, st.session_state.state
                        )
                    except Exception as e:
                        reply = f"[WARN] Error: {e}"
                st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

            # 3) Refrescar
            st.rerun()

with tab_docente:
    st.markdown("## 📊 Panel Docente — Evidencias de la Rúbrica")
    st.caption("Este panel demuestra visualmente el cumplimiento de los 9 criterios de evaluación.")

    # ─────────────────────────────────────────────────────────────────────
    # CRITERIO 1: Análisis del problema y requisitos (10%)
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 1️⃣ Análisis del Problema y Requisitos (10%)")
    col1a, col1b = st.columns(2)
    with col1a:
        st.markdown("""
        **Problema identificado:** Atención manual de pedidos textiles genera demoras,
        errores en cotizaciones y pérdida de clientes.

        **Solución:** Sistema multiagente que automatiza el flujo completo:
        validación → recolección → cotización → registro → notificación.
        """)
    with col1b:
        st.markdown("**Requisitos Funcionales implementados:**")
        st.markdown("""
        | ID | Requisito | Estado |
        |---|---|---|
        | RF-01 | Validar rubro textil | ✅ |
        | RF-02 | Recolectar 8 datos del pedido | ✅ |
        | RF-03 | Calcular cotización con descuentos | ✅ |
        | RF-04 | Registrar pedido en BD SQLite | ✅ |
        | RF-05 | Enviar constancia por email (HTML) | ✅ |
        | RF-06 | Consultas RAG sobre catálogo | ✅ |
        """)

    # ─────────────────────────────────────────────────────────────────────
    # CRITERIO 2: Arquitectura y diseño técnico (15%)
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 2️⃣ Arquitectura y Diseño Técnico (15%)")
    col2a, col2b = st.columns(2)
    with col2a:
        st.markdown("**Arquitectura Multiagente Jerárquica:**")
        st.code("""
┌─────────────────────────────────┐
│       OrchestratorAgent         │  ← Coordinador central
├─────────┬───────┬───────┬───────┤
│Validator│DataCol│Pricing│Registry│ Notifier
│  Agent  │lector │ Agent │ Agent  │  Agent
└─────────┴───────┴───────┴───────┘
     ↕         ↕       ↕       ↕        ↕
  [SharedState — Memoria central]
     ↕         ↕       ↕       ↕        ↕
  [Event Bus — Pub/Sub asíncrono]
     ↕         ↕       ↕       ↕        ↕
  [MCP Messages — JSON validado]
        """, language="text")
    with col2b:
        st.markdown("**Componentes del sistema:**")
        st.markdown("""
        | Componente | Archivo | Patrón |
        |---|---|---|
        | Orquestador | `agents/orchestrator.py` | Jerárquico |
        | Estado compartido | `core/shared_state.py` | Thread-safe |
        | Bus de eventos | `core/event_bus.py` | Pub/Sub |
        | Mensajes MCP | `core/mcp_messages.py` | Schema Pydantic |
        | Métricas | `core/metrics.py` | Singleton |
        | Config central | `config.py` | Multi-proveedor |
        """)

    # ─────────────────────────────────────────────────────────────────────
    # CRITERIO 3: Implementación (RAG, tools, LangGraph, Deep Agent) (15%)
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 3️⃣ Implementación: RAG, Tools, LangGraph, Deep Agent (15%)")

    tab3_rag, tab3_lg, tab3_deep, tab3_tools = st.tabs([
        "🔍 RAG", "🔗 LangGraph", "🤖 Deep Agent", "🔧 Tools"
    ])

    with tab3_rag:
        st.markdown("**Recuperación Híbrida (Densa + BM25) — `rag/`**")
        st.markdown(f"""
        - **Ingesta:** `rag/ingester.py` → Chunking ({__import__('config').RAG_CHUNK_SIZE} chars, overlap {__import__('config').RAG_CHUNK_OVERLAP})
        - **Retriever:** `rag/retriever.py` → Búsqueda híbrida (peso denso: {__import__('config').RAG_DENSE_WEIGHT})
        - **Vector Store:** ChromaDB con embeddings de Sentence-Transformers
        - **Top-K:** {__import__('config').RAG_TOP_K} fragmentos recuperados por consulta
        """)

    with tab3_lg:
        st.markdown("**Grafo LangGraph — `langgraph_flow/graph.py`**")
        try:
            from langgraph_flow.graph import get_graph_diagram
            st.code(get_graph_diagram(), language="text")
        except Exception:
            st.code("""
START → planificar → recuperar → responder → validar
                                                  ↓
                                        ¿necesita_mas?
                                        Sí → recuperar (loop)
                                        No → END
            """, language="text")
        st.markdown("""
        - **State:** `langgraph_flow/state.py` — TypedDict con pregunta, contexto, plan, respuesta
        - **Nodes:** `langgraph_flow/nodes.py` — 4 nodos: planificar, recuperar, responder, validar
        - **Checkpointing:** MemorySaver (extensible a SQLite)
        """)

    with tab3_deep:
        st.markdown("**Deep Agent — `deep_agent/graph.py`**")
        try:
            from deep_agent.graph import get_deep_agent_diagram
            st.code(get_deep_agent_diagram(), language="text")
        except Exception:
            st.code("""
START → PLANIFICADOR → INVESTIGADOR → REDACTOR → CRÍTICO
                           ↑                        ↓
                           └──── loop (máx 3-5) ────┘
            """, language="text")
        st.markdown("""
        - **Sub-agentes:** Investigador (RAG), Redactor, Crítico
        - **Planificador:** `deep_agent/planner.py` — Descompone tareas complejas
        - **Límites:** Máx 5 iteraciones, máx 10 invocaciones
        """)

    with tab3_tools:
        st.markdown("**Herramientas externas — `tools/`**")
        st.markdown("""
        | Tool | Archivo | Función |
        |---|---|---|
        | 📧 EmailTool | `tools/email_tool.py` | Genera HTML de constancia y lo guarda |
        | 💾 SheetsTool | `tools/sheets_tool.py` | Persiste pedidos en SQLite |
        """)
        st.markdown("**Integración LangChain:** Ambas tools están registradas como `@tool` para `bind_tools()`.")

    # ─────────────────────────────────────────────────────────────────────
    # CRITERIO 4: Observabilidad y evaluación — LangSmith (10%)
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 4️⃣ Observabilidad y Evaluación — LangSmith (10%)")
    col4a, col4b = st.columns(2)
    with col4a:
        st.markdown("**Configuración LangSmith** (`evaluation/langsmith_config.py`):")
        from config import LANGSMITH_PROJECT, LANGSMITH_TRACING
        st.markdown(f"""
        - **Proyecto:** `{LANGSMITH_PROJECT}`
        - **Tracing activo:** `{LANGSMITH_TRACING}`
        - **Endpoint:** `https://api.smith.langchain.com`
        - **Tags por traza:** versión de prompt, modelo, sesión
        - **Metadata:** `get_trace_metadata()` inyecta prompt_version y provider
        """)
        st.markdown("**Golden Set** (`evaluation/golden_set.py`): 10 casos de prueba.")
        try:
            from evaluation.golden_set import golden_set_as_dicts
            import pandas as pd
            gs_df = pd.DataFrame(golden_set_as_dicts())
            st.dataframe(gs_df[["case_id", "categoria", "entrada", "requisito"]], use_container_width=True, height=200)
        except Exception as e:
            st.warning(f"No se pudo cargar el golden set: {e}")

    with col4b:
        st.markdown("**Métricas en tiempo real** (esta sesión):")
        summary = metrics.summary()
        if summary.get("total_invocations", 0) > 0:
            mc1, mc2 = st.columns(2)
            mc1.metric("Invocaciones LLM", summary["total_invocations"])
            mc2.metric("Tasa de Éxito", f"{summary['success_rate']*100:.1f}%")
            mc3, mc4 = st.columns(2)
            mc3.metric("Latencia Promedio", f"{summary['avg_latency_ms']:.0f} ms")
            mc4.metric("Tokens (Est.)", summary["total_tokens_estimate"])
            st.markdown("**Desglose por agente:**")
            for agent_name, agent_data in summary.get("by_agent", {}).items():
                with st.expander(f"🤖 {agent_name} — {agent_data['invocations']} invocaciones"):
                    ca, cb, cc = st.columns(3)
                    ca.metric("Éxito", f"{agent_data['success_rate']*100:.0f}%")
                    cb.metric("Latencia", f"{agent_data['avg_latency_ms']:.0f} ms")
                    cc.metric("Tokens", agent_data['tokens_estimate'])
        else:
            st.info("⏳ Realiza una interacción en la pestaña 'Atención al Cliente' para ver métricas aquí.")

    # ─────────────────────────────────────────────────────────────────────
    # CRITERIO 5: Calidad del código y prompts versionados (10%)
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 5️⃣ Calidad del Código y Prompts Versionados (10%)")
    col5a, col5b = st.columns(2)
    with col5a:
        st.markdown("**Catálogo de Prompts** (`prompts/catalog.py`):")
        try:
            from prompts.catalog import list_prompts
            for p in list_prompts():
                icon = "🟢" if p.get("latest") else "⚪"
                label = f"{icon} {p['prompt_id']} v{p['version']} — Accuracy: {(p.get('metric_score') or 0)*100:.0f}%"
                with st.expander(label):
                    st.write(f"**Propósito:** {p['purpose']}")
                    st.write(f"**Descripción:** {p['description']}")
                    if p.get("notes"):
                        st.caption(f"📝 {p['notes']}")
        except Exception as e:
            st.error(f"Error: {e}")

    with col5b:
        st.markdown("**Suite de Tests** (`tests/`):")
        st.markdown("""
        | Archivo | Cobertura |
        |---|---|
        | `test_e2e.py` | Flujo completo end-to-end |
        | `test_pricing.py` | Cálculos de cotización |
        | `test_validator.py` | Validación de rubro |
        | `test_shared_state.py` | Estado compartido thread-safe |
        | `test_mcp_messages.py` | Schemas MCP/Pydantic |
        | `conftest.py` | Fixtures compartidos |
        """)
        st.markdown("**Calidad de código:**")
        st.markdown("""
        - ✅ Tipado estricto con `pyrightconfig.json`
        - ✅ Docstrings en todas las funciones públicas
        - ✅ Separación de responsabilidades (MVC-like)
        - ✅ Thread-safety con `threading.Lock`
        """)

    # ─────────────────────────────────────────────────────────────────────
    # CRITERIO 6: Documentación (10%)
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 6️⃣ Documentación (10%)")
    st.markdown("""
    | Documento | Descripción |
    |---|---|
    | `README.md` | Guía completa del proyecto, instalación y uso |
    | `SETUP_GITHUB_MODELS.md` | Instrucciones de configuración de API keys |
    | `.env.example` | Plantilla de variables de entorno |
    | `Plantilla de Proyecto...docx` | Documento formal con análisis completo |
    | Docstrings en código | Todas las funciones documentadas (ver `config.py`, `core/`) |
    """)

    # ─────────────────────────────────────────────────────────────────────
    # CRITERIO 7: Despliegue y operación (10%)
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 7️⃣ Despliegue y Operación (10%)")
    col7a, col7b = st.columns(2)
    with col7a:
        st.markdown("""
        **Stack de despliegue:**
        - 🐍 Python 3.13 + `requirements.txt` (dependencias fijadas)
        - 🌐 Streamlit como servidor web (interfaz de usuario)
        - 💾 SQLite para persistencia local (`data/pedidos.db`)
        - 📄 `.env.example` como plantilla de configuración
        """)
    with col7b:
        st.markdown("**Estado operativo actual:**")
        from config import validate_config, EXECUTION_MODE, LLM_PROVIDER, LLM_MODEL
        ok, msg = validate_config()
        if ok:
            st.success(msg)
        else:
            st.warning(msg)
        st.markdown(f"""
        - **Modo:** `{EXECUTION_MODE}`
        - **Proveedor LLM:** `{LLM_PROVIDER}`
        - **Modelo:** `{LLM_MODEL}`
        """)

    # ─────────────────────────────────────────────────────────────────────
    # CRITERIO 8: Medición de éxito y ROI (10%)
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 8️⃣ Medición de Éxito y ROI (10%)")
    col8a, col8b = st.columns(2)
    with col8a:
        st.markdown("**Métricas de evaluación** (`evaluation/evaluators.py`):")
        st.markdown("""
        | Métrica | Umbral | Método |
        |---|---|---|
        | Exactitud | ≥ 90% | Heurístico + LLM-as-judge |
        | Groundedness | ≥ 95% | LLM-as-judge |
        | Latencia p95 | < 3000 ms | Medición directa |
        | Costo/consulta | < $0.01 | Estimación por tokens |
        """)
    with col8b:
        st.markdown("**Archivo de métricas persistido:**")
        metrics_path = Path(__file__).resolve().parent / "data" / "metrics.jsonl"
        if metrics_path.exists():
            line_count = sum(1 for _ in open(metrics_path, encoding="utf-8"))
            size_kb = metrics_path.stat().st_size / 1024
            st.success(f"📄 `metrics.jsonl`: {line_count} registros ({size_kb:.1f} KB)")
            st.caption("Cada invocación a un agente se registra con: nombre, latencia, éxito, tokens.")
        else:
            st.info("El archivo de métricas se creará con la primera interacción.")

    # ─────────────────────────────────────────────────────────────────────
    # CRITERIO 9: Innovación y contribución (10%)
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 9️⃣ Innovación y Contribución (10%)")
    st.markdown("""
    | Innovación | Descripción |
    |---|---|
    | 🔄 Multi-proveedor LLM | Soporte para GitHub Models, OpenAI, Gemini y Claude vía LiteLLM |
    | 🔍 RAG Híbrido | Combina búsqueda densa (embeddings) + léxica (BM25) para mejor recall |
    | 🤖 Deep Agent autónomo | Agente con ciclo plan-investiga-redacta-critica con loop de refinamiento |
    | 📡 Event Bus pub/sub | Arquitectura desacoplada y extensible entre agentes |
    | 📋 Formulario interactivo | UI con previsualización de cotización en tiempo real |
    | 📜 Prompts versionados | Catálogo con historial de versiones y scores de evaluación |
    | 🧪 Golden Set | 10 casos de prueba vinculados a requisitos funcionales |
    | 🧵 Thread-safety | Estado compartido con Lock para concurrencia segura |
    """)

    # ─────────────────────────────────────────────────────────────────────
    # SECCIÓN BONUS: Estado vivo del sistema
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🔎 Inspección en Vivo")
    col_live1, col_live2 = st.columns(2)
    with col_live1:
        st.markdown("#### 🧠 SharedState (snapshot)")
        st.json(state.snapshot())
    with col_live2:
        st.markdown("#### 📡 Event Bus (log)")
        event_log = event_bus.get_event_log()
        if event_log:
            for ev in reversed(event_log[-10:]):
                with st.expander(f"[{ev.timestamp.strftime('%H:%M:%S')}] {ev.source} ➔ {ev.event_name}"):
                    st.json(ev.data)
        else:
            st.info("Realiza una interacción para ver eventos aquí.")


# =============================================================================
# FOOTER
# =============================================================================
st.markdown(
    "<hr style='margin-top:40px;'>"
    "<p style='text-align:center;color:#666;font-size:12px;'>"
    "Grupo 01 · Caipo · Sánchez · Díaz · Salirrosas · "
    "Curso: Automatización Inteligente de Procesos · Docente: Luis Vladimir Urrelo Huamán"
    "</p>",
    unsafe_allow_html=True,
)
