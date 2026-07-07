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

# La interfaz principal es de un solo panel para el cliente
if True:
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
