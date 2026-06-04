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

import streamlit as st

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
    for k in ("orchestrator", "state", "messages"):
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
        ConversationStage.COMPLETE: "✅ Completado",
        ConversationStage.REJECTED: "❌ Rechazado",
    }
    st.markdown(f"**Etapa:** {stage_emojis.get(state.stage, state.stage.value)}")
    st.divider()

    # Validación
    if state.validation_result:
        v = state.validation_result
        icon = "✅" if v.is_textile else "❌"
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

# Tabs: Chat, Métricas, Eventos MCP, RAG, Deep Agent, Evaluación
tab_chat, tab_metrics, tab_events, tab_rag, tab_deep, tab_eval = st.tabs([
    "💬 Chat", "📊 Métricas", "🔍 Trazabilidad MCP",
    "📚 RAG Demo", "🤖 Deep Agent", "🧪 Evaluación"
])

# --------- TAB CHAT ----------
with tab_chat:
    # Renderizar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])

    # Input del usuario
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
                    reply = f"⚠️ Error: {e}"
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})

        # 3) Refrescar la sidebar (que muestra el estado actualizado)
        st.rerun()


# --------- TAB MÉTRICAS ----------
with tab_metrics:
    summary = metrics.summary()
    if summary.get("total_invocations", 0) == 0:
        st.info("Aún no hay invocaciones registradas. Envía un mensaje para generar métricas.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total invocaciones", summary["total_invocations"])
        c2.metric("Tasa de éxito", f"{summary['success_rate'] * 100:.1f}%")
        c3.metric("Tokens estimados", f"{summary['total_tokens_estimate']:,}")
        c4.metric("Latencia avg (ms)", f"{summary['avg_latency_ms']:.1f}")

        st.divider()
        st.markdown("#### Por agente")
        by_agent_rows = []
        for agent_name, stats in summary["by_agent"].items():
            by_agent_rows.append({
                "Agente": agent_name,
                "Invocaciones": stats["invocations"],
                "Éxito %": f"{stats['success_rate'] * 100:.0f}",
                "Lat. avg (ms)": f"{stats['avg_latency_ms']:.1f}",
                "Lat. max (ms)": f"{stats['max_latency_ms']:.1f}",
                "Tokens": stats["tokens_estimate"],
            })
        st.dataframe(by_agent_rows, use_container_width=True, hide_index=True)


# --------- TAB TRAZABILIDAD MCP ----------
with tab_events:
    st.markdown("#### 📜 Últimos mensajes MCP")
    st.caption("Comunicación entre agentes vía JSON Schema validado (Pydantic).")

    msgs = state.message_history[-15:][::-1]  # últimos 15, más recientes primero
    if not msgs:
        st.info("No hay mensajes MCP aún.")
    else:
        for m in msgs:
            with st.expander(
                f"`{m.message_type.value}` · "
                f"{m.sender.value} → {m.receiver.value} · "
                f"{m.timestamp.strftime('%H:%M:%S')}"
            ):
                st.json(m.payload)

    st.divider()
    st.markdown("#### 🎯 Eventos del Event Bus")
    events = event_bus.get_event_log()[-15:][::-1]
    if not events:
        st.info("No hay eventos publicados aún.")
    else:
        for ev in events:
            with st.expander(
                f"`{ev.event_name}` · {ev.source.value} · "
                f"{ev.timestamp.strftime('%H:%M:%S')}"
            ):
                st.json(ev.data)


# --------- TAB RAG DEMO ----------
with tab_rag:
    st.markdown("### 📚 RAG — Retrieval-Augmented Generation")
    st.caption(
        "Subsistema de recuperación de información del catálogo (§3.3). "
        "Usa chunking recursivo + embeddings + ChromaDB + BM25 híbrido."
    )

    rag_query = st.text_input(
        "Pregunta sobre el catálogo:",
        placeholder="¿Cuánto cuestan los polos con estampado?",
        key="rag_input",
    )

    col_rag1, col_rag2 = st.columns(2)
    with col_rag1:
        rag_k = st.slider("Fragmentos a recuperar (k)", 1, 8, 4)
    with col_rag2:
        show_scores = st.checkbox("Mostrar scores", value=True)

    if st.button("🔍 Buscar en el catálogo", key="rag_search") and rag_query:
        with st.spinner("Buscando en el vector store..."):
            try:
                from rag.retriever import HybridRetriever
                ret = HybridRetriever(k=rag_k)
                if show_scores:
                    results = ret.query_with_scores(rag_query, k=rag_k)
                    for i, (doc, score) in enumerate(results):
                        with st.expander(f"📄 Fragmento {i+1} (score: {score:.3f})"):
                            st.markdown(doc)
                else:
                    results = ret.query(rag_query, k=rag_k)
                    for i, doc in enumerate(results):
                        with st.expander(f"📄 Fragmento {i+1}"):
                            st.markdown(doc)

                # Generar respuesta con LangGraph
                st.divider()
                st.markdown("#### 💬 Respuesta generada (LangGraph RAG)")
                with st.spinner("Generando respuesta con contexto..."):
                    try:
                        from langgraph_flow.graph import run_query
                        lg_result = run_query(rag_query)
                        st.success(lg_result.get("respuesta", "Sin respuesta"))
                        st.caption(f"🔁 Iteraciones: {lg_result.get('iteraciones', 0)} | "
                                   f"📋 Plan: {lg_result.get('plan', [])}")
                    except Exception as e:
                        st.warning(f"LangGraph no disponible: {e}")
            except Exception as e:
                st.error(f"Error en RAG: {e}")

    # Botón de ingesta
    st.divider()
    st.markdown("#### 🔄 Gestión del Vector Store")
    if st.button("📥 Re-ingestar documentos", key="rag_ingest"):
        with st.spinner("Ingestando documentos..."):
            try:
                from rag.ingester import ingest
                count = ingest(force=True)
                st.success(f"✅ {count} chunks ingestados en ChromaDB")
            except Exception as e:
                st.error(f"Error en ingesta: {e}")


# --------- TAB DEEP AGENT ----------
with tab_deep:
    st.markdown("### 🤖 Deep Agent — Planificación + Sub-agentes")
    st.caption(
        "Patrón Deep Agent (§3.6): planificador + Investigador + Redactor + Crítico. "
        "Resuelve tareas complejas con ciclos de refinamiento."
    )

    deep_task = st.text_area(
        "Describe la tarea:",
        placeholder="Compara precios de polos con y sin estampado para 100 unidades, incluyendo descuentos",
        key="deep_input",
        height=80,
    )
    deep_max_iter = st.slider("Máx iteraciones", 1, 5, 3, key="deep_iter")

    if st.button("🚀 Ejecutar Deep Agent", key="deep_run") and deep_task:
        with st.spinner("Deep Agent trabajando..."):
            try:
                from deep_agent.graph import run_deep_agent
                result = run_deep_agent(deep_task, max_iterations=deep_max_iter)

                # Mostrar resultados paso a paso
                st.markdown("#### 📋 Plan generado")
                for i, paso in enumerate(result.get("plan", []), 1):
                    st.markdown(f"{i}. {paso}")

                st.markdown("#### 🔍 Hallazgos del Investigador")
                for h in result.get("hallazgos", []):
                    st.markdown(f"- {h}")

                st.markdown("#### ✅ Evaluación del Crítico")
                critica = result.get("critica", {})
                if critica:
                    icon = "✅" if critica.get("aprobado") else "❌"
                    st.markdown(f"{icon} Puntuación: **{critica.get('puntuacion', 'N/A')}/10**")
                    for obs in critica.get("observaciones", []):
                        st.markdown(f"  - {obs}")

                st.divider()
                st.markdown("#### 💬 Respuesta Final")
                st.success(result.get("respuesta_final", "Sin respuesta final"))
                st.caption(f"🔁 Iteraciones: {result.get('iteracion', 0)}/{deep_max_iter}")

            except Exception as e:
                st.error(f"Error en Deep Agent: {e}")

    # Diagrama
    with st.expander("📐 Diagrama del Deep Agent"):
        st.code("""
    START → PLANIFICADOR → INVESTIGADOR → REDACTOR → CRÍTICO
                                ↑                        │
                                └── (si no aprobado) ─────┘
                                       (loop, máx N iter)
        """, language="text")


# --------- TAB EVALUACIÓN ----------
with tab_eval:
    st.markdown("### 🧪 Plan de Evaluación — Golden Set")
    st.caption(
        "§5: Evaluación contra el golden set con métricas de exactitud, "
        "groundedness, latencia y costo. LangSmith para observabilidad."
    )

    # Mostrar el golden set
    with st.expander("📋 Ver Golden Set (10 casos)", expanded=False):
        try:
            from evaluation.golden_set import golden_set_as_dicts
            gs_data = golden_set_as_dicts()
            st.dataframe(gs_data, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error cargando golden set: {e}")

    # Catálogo de prompts
    with st.expander("📝 Catálogo de Prompts Versionado (§6)", expanded=False):
        try:
            from prompts.catalog import list_prompts
            prompts_data = list_prompts()
            st.dataframe(prompts_data, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error cargando prompts: {e}")

    # Ejecutar evaluación
    st.divider()
    eval_col1, eval_col2 = st.columns(2)
    with eval_col1:
        eval_categoria = st.selectbox(
            "Categoría", ["Todas", "validacion", "rag", "cotizacion", "e2e"],
            key="eval_cat",
        )
    with eval_col2:
        eval_verbose = st.checkbox("Modo verbose", value=False, key="eval_verbose")

    if st.button("▶️ Ejecutar evaluación del Golden Set", key="eval_run"):
        cat = None if eval_categoria == "Todas" else eval_categoria
        with st.spinner("Ejecutando evaluación..."):
            try:
                from evaluation.run_eval import run_golden_set_evaluation
                results = run_golden_set_evaluation(
                    categoria=cat,
                    verbose=eval_verbose,
                )

                # Métricas globales
                st.markdown("#### 📊 Métricas Globales (§5.2)")
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Casos evaluados", results["total_cases"])
                mc2.metric("Aprobados", f"{results['aprobados']}/{results['total_cases']}")
                mc3.metric("Exactitud avg", f"{results['avg_exactitud']:.1%}")
                mc4.metric("Latencia avg", f"{results['avg_latencia_ms']:.0f} ms")

                # Tabla de resultados
                st.markdown("#### 📋 Resultados por caso")
                eval_rows = []
                for r in results["results"]:
                    eval_rows.append({
                        "ID": r["case_id"],
                        "Aprobado": "✅" if r["aprobado"] else "❌",
                        "Exactitud": f"{r['exactitud']:.2f}",
                        "Groundedness": f"{r['groundedness']:.2f}",
                        "Latencia (ms)": f"{r['latencia_ms']:.0f}",
                    })
                st.dataframe(eval_rows, use_container_width=True, hide_index=True)

                # Decisión
                if results["tasa_aprobacion"] >= 0.8:
                    st.success("✅ DECISIÓN: Sistema APROBADO — Cumple umbrales de calidad")
                else:
                    st.warning("❌ DECISIÓN: ITERAR — No cumple umbrales mínimos")

            except Exception as e:
                st.error(f"Error en evaluación: {e}")

    # LangSmith status
    st.divider()
    st.markdown("#### 🔗 LangSmith — Observabilidad (§5.3)")
    try:
        from evaluation.langsmith_config import check_langsmith_connection, LANGSMITH_PROJECT
        ok, msg = check_langsmith_connection()
        if ok:
            st.success(f"✅ {msg}")
        else:
            st.info(f"ℹ️ {msg}")
        st.caption(f"Proyecto: `{LANGSMITH_PROJECT}`")
    except Exception as e:
        st.info(f"LangSmith: {e}")


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

