"""
app.py — Frontend web del sistema multiagente con Streamlit.

Provee una interfaz visual completa con dos pestañas:
  - 🧵 Realizar Pedido: Chat + formulario para clientes.
  - 📦 Compra de Materiales: Flujo administrativo con HITL.
  - Sidebar con estado en vivo, métricas y eventos.

Uso:
    streamlit run app.py
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
from datetime import date, timedelta

# Asegurar que el paquete sea importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # type: ignore

from agents.orchestrator import Orchestrator
from core.shared_state import SharedState, ConversationStage
from core.metrics import metrics
from core.event_bus import event_bus
from config import (
    EXECUTION_MODE, EMPRESA_NOMBRE, LLM_PROVIDER, LLM_MODEL,
    LLM_API_BASE, PRICE_TABLE_PATH, BASE_DIR,
)


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
# Inicialización de estado
# =============================================================================
def init_session() -> None:
    """Inicializa o resetea el estado de la sesión Streamlit."""
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = Orchestrator()
    if "state" not in st.session_state:
        st.session_state.state = SharedState()
    if "messages" not in st.session_state:
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
    # Estado del Proceso 2
    if "materials_state" not in st.session_state:
        st.session_state.materials_state = SharedState()
    if "materials_results" not in st.session_state:
        st.session_state.materials_results = None
    if "materials_step" not in st.session_state:
        st.session_state.materials_step = "idle"  # idle, planning, awaiting_approval, approved, completed


def reset_session() -> None:
    """Reinicia toda la conversación."""
    for k in ("orchestrator", "state", "messages", "form_submitted",
              "materials_state", "materials_results", "materials_step"):
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
        # Proceso 2
        ConversationStage.PLANNING_MATERIALS: "📦 Planificando materiales",
        ConversationStage.ESTIMATING_BUDGET: "💰 Estimando presupuesto",
        ConversationStage.WAITING_BUDGET_APPROVAL: "⏳ Aprobación HITL",
        ConversationStage.PURCHASING: "🛒 Comprando",
        ConversationStage.WAITING_RECEPTION: "📬 Esperando recepción",
        ConversationStage.NOTIFYING_PRODUCTION: "📢 Notificando producción",
        ConversationStage.PURCHASE_COMPLETE: "✅ Compra completada",
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
# PANEL PRINCIPAL: Pestañas
# =============================================================================
st.title("🧵 Fábrica de Ropa — Sistema Multiagente")
st.caption(
    "Orquestador + 10 agentes especializados · "
    "2 procesos: Realizar Pedido + Compra de Materiales"
)

tab_pedido, tab_materiales = st.tabs(["🧵 Realizar Pedido", "📦 Compra de Materiales"])

# =============================================================================
# TAB 1: Realizar Pedido (flujo existente)
# =============================================================================
with tab_pedido:
    # Renderizar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])

    # ─────────────────────────────────────────────────────────────────────────
    # FORMULARIO INTERACTIVO DE PEDIDO
    # ─────────────────────────────────────────────────────────────────────────
    _show_form = (
        state.stage == ConversationStage.COLLECTING_DATA
        and not st.session_state.get("form_submitted", False)
    )

    if _show_form:
        with open(PRICE_TABLE_PATH, encoding="utf-8") as _f:
            _pt = json.load(_f)

        st.markdown("---")
        st.markdown("### 📋 Completemos los detalles de tu cotización")
        st.caption("Selecciona los detalles de tu pedido y obtendrás la cotización al instante.")

        with st.form("order_form", clear_on_submit=False):
            # ── Datos del cliente ──
            st.markdown("#### 👤 Datos del cliente")
            fc1, fc2 = st.columns(2)
            with fc1:
                form_nombre = st.text_input("Nombre completo *", placeholder="Juan Pérez", key="f_nombre")
            with fc2:
                form_email = st.text_input("Email *", placeholder="juan@empresa.com", key="f_email")

            st.markdown("---")

            # ── Detalles de la prenda ──
            st.markdown("#### 👕 Detalles del pedido")
            _prenda_options = {
                k: f"{k.capitalize()} — S/ {v['precio_unitario']:.2f}"
                for k, v in _pt["prendas"].items()
            }
            fp1, fp2 = st.columns(2)
            with fp1:
                form_prenda_key = st.selectbox(
                    "Tipo de prenda *", options=list(_prenda_options.keys()),
                    format_func=lambda x: _prenda_options[x], key="f_prenda",
                )
            with fp2:
                form_cantidad = st.number_input(
                    "Cantidad (unidades) *", min_value=1, max_value=10000, value=50, step=10, key="f_cantidad",
                )

            fp3, fp4 = st.columns(2)
            with fp3:
                form_talla = st.selectbox("Talla *", options=["XS", "S", "M", "L", "XL", "XXL"], index=2, key="f_talla")
            with fp4:
                form_color = st.selectbox(
                    "Color *", options=["Blanco", "Negro", "Azul", "Rojo", "Gris",
                                        "Verde", "Amarillo", "Celeste", "Rosa", "Naranja"], key="f_color",
                )

            _acabado_labels = {
                "ninguno": "Sin acabado (S/ 0.00)",
                "estampado": f"Estampado (+S/ {_pt['acabados']['estampado']:.2f})",
                "bordado": f"Bordado (+S/ {_pt['acabados']['bordado']:.2f})",
            }
            form_acabado = st.radio(
                "Acabado *", options=list(_acabado_labels.keys()),
                format_func=lambda x: _acabado_labels[x], horizontal=True, key="f_acabado",
            )

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

            submitted = st.form_submit_button("📋 Generar Cotización", use_container_width=True, type="primary")

            if submitted:
                errors = []
                if not form_nombre.strip():
                    errors.append("Nombre es obligatorio")
                if not form_email.strip() or "@" not in form_email:
                    errors.append("Email válido es obligatorio")

                if errors:
                    st.error("⚠️ " + " · ".join(errors))
                else:
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

                    try:
                        reply = st.session_state.orchestrator.handle_form_submission(
                            form_data, st.session_state.state
                        )
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
                        st.error(f"⚠️ Error al procesar: {e}")

    # Botones interactivos de confirmación
    if state.stage == ConversationStage.WAITING_CONFIRMATION and state.quote_result:
        st.markdown("---")
        st.info("💡 Tu cotización está lista. Por favor, revísala y confirma tu pedido.")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            st.download_button(
                label="📥 Descargar Cotización",
                data=state.quote_result.resumen_texto,
                file_name=f"cotizacion_{state.order_data.nombre or 'cliente'}.txt",
                mime="text/plain",
                use_container_width=True
            )
            
        with col2:
            if st.button("✅ Confirmar Pedido", type="primary", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": "Sí, confirmo el pedido."})
                with st.spinner("Registrando pedido y generando boleta..."):
                    try:
                        reply = st.session_state.orchestrator.handle_user_message("Sí, confirmo", st.session_state.state)
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                    except Exception as e:
                        st.error(f"⚠️ Error: {e}")
                st.rerun()

        with col3:
            if st.button("❌ Cancelar Pedido", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": "No, deseo cancelar."})
                with st.spinner("Cancelando..."):
                    try:
                        reply = st.session_state.orchestrator.handle_user_message("No, deseo cancelar", st.session_state.state)
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                    except Exception as e:
                        st.error(f"⚠️ Error: {e}")
                st.rerun()

    # Input de chat
    _show_chat_input = (
        state.stage in (
            ConversationStage.INITIAL,
            ConversationStage.VALIDATING,
            ConversationStage.WAITING_CONFIRMATION,
            ConversationStage.COLLECTING_DATA,
        )
        and state.stage != ConversationStage.COMPLETE
        and state.stage != ConversationStage.REJECTED
    )

    if _show_chat_input:
        if user_msg := st.chat_input("Escribe tu mensaje..."):
            st.session_state.messages.append({"role": "user", "content": user_msg})
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_msg)

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
            st.rerun()


# =============================================================================
# TAB 2: Compra de Materiales (Proceso 2)
# =============================================================================
with tab_materiales:
    st.markdown("### 📦 Proceso 2: Compra de Materiales")
    st.caption(
        "Flujo administrativo: MaterialPlanner → Budget → Approval (HITL) → "
        "Supplier → Production"
    )

    # Diagrama del flujo
    with st.expander("📊 Ver diagrama del flujo", expanded=False):
        st.code("""
    ┌──────────────────┐
    │      START        │
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │ PLANIFICAR        │  Genera lista de materiales
    │ MATERIALES        │  desde pedidos pendientes
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │ ESTIMAR           │  Calcula presupuesto con
    │ PRESUPUESTO       │  RAG + catálogo
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │ APROBAR           │  ⚠️ HITL: Human-in-the-Loop
    │ PRESUPUESTO       │  Espera aprobación humana
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │ SELECCIONAR       │  Elige proveedor y
    │ PROVEEDOR         │  registra compra
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │ NOTIFICAR         │  Avisa a producción
    │ PRODUCCIÓN        │  que materiales llegaron
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │       END         │
    └──────────────────┘
        """, language=None)

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 1: Iniciar planificación
    # ─────────────────────────────────────────────────────────────────────────
    mat_step = st.session_state.materials_step

    if mat_step == "idle":
        st.markdown("#### 🚀 Iniciar planificación semanal de materiales")
        st.markdown(
            "Este proceso analiza los pedidos pendientes, revisa el **Almacén Inteligente**, "
            "asigna el stock disponible y estima un presupuesto solo por los faltantes."
        )

        # DASHBOARD DE INVENTARIO
        st.markdown("#### 🏭 Almacén Inteligente (Inventario en vivo)")
        inv_cols = st.columns(3)
        inv = st.session_state.materials_state.inventory
        
        # Diccionario de capacidades máximas para las barras
        max_cap = {"tela algodón": 1000, "hilo industrial": 50, "etiquetas": 1000, "botones": 1000, "tinta estampado": 20, "hilo bordado": 20}
        
        for idx, (mat, qty) in enumerate(inv.items()):
            col = inv_cols[idx % 3]
            with col:
                cap = max_cap.get(mat, qty * 2 or 100)
                pct = min(1.0, qty / cap)
                color = "green" if pct > 0.3 else "red"
                st.markdown(f"**{mat.title()}**: {qty:.0f} u.")
                st.progress(pct)

        st.divider()

        col_start, col_info = st.columns([1, 2])
        with col_start:
            if st.button("▶️ Ejecutar Planificación y Revisar Stock", type="primary", use_container_width=True):
                with st.spinner("🔄 Cruzando datos de pedidos con inventario..."):
                    try:
                        results = st.session_state.orchestrator.handle_materials_purchase(
                            st.session_state.materials_state
                        )
                        st.session_state.materials_results = results
                        st.session_state.materials_step = "awaiting_approval"
                        st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ Error: {e}")

        with col_info:
            # Mostrar proveedores disponibles
            suppliers_path = BASE_DIR / "data" / "suppliers.json"
            if suppliers_path.exists():
                with open(suppliers_path, encoding="utf-8") as f:
                    suppliers = json.load(f).get("proveedores", [])
                st.markdown("**Proveedores disponibles para compras:**")
                for s in suppliers:
                    st.markdown(
                        f"- 🏢 **{s['nombre']}** · "
                        f"Cumplimiento: {s['historial_cumplimiento']*100:.0f}% · "
                        f"Entrega: {s['tiempo_entrega_dias']} días"
                    )

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 2: Mostrar resultados y esperar aprobación HITL
    # ─────────────────────────────────────────────────────────────────────────
    elif mat_step == "awaiting_approval":
        results = st.session_state.materials_results

        if results:
            # Mostrar progreso
            st.markdown("#### 📋 Progreso del proceso")
            for etapa in results.get("etapas", []):
                st.markdown(f"  {etapa}")

            st.divider()

            # Mostrar materiales planificados (DIVIDIDOS)
            if "material_plan" in results:
                mp = results["material_plan"]
                st.markdown("#### 📦 Asignación Inteligente de Materiales")
                
                col_stock, col_buy = st.columns(2)
                
                with col_stock:
                    st.success("🟢 Tomado del Almacén (Ahorro)")
                    mat_stock = []
                    for m, c in zip(mp["materiales"], mp.get("en_stock", [])):
                        if c > 0:
                            mat_stock.append({"Material": m, "Cantidad (Stock)": c})
                    if mat_stock:
                        st.table(mat_stock)
                    else:
                        st.info("No se pudo usar stock (Almacén vacío)")
                        
                with col_buy:
                    st.error("🔴 Faltante por Comprar (Presupuesto)")
                    mat_buy = []
                    for m, c in zip(mp["materiales"], mp.get("a_comprar", mp["cantidades"])):
                        if c > 0:
                            mat_buy.append({"Material": m, "Cantidad (Comprar)": c})
                    if mat_buy:
                        st.table(mat_buy)
                    else:
                        st.success("¡Tenemos todo en stock! No se requiere compra.")

            # Mostrar presupuesto
            if "budget" in results:
                b = results["budget"]
                st.markdown("#### 💰 Presupuesto Estimado")
                bc1, bc2 = st.columns(2)
                bc1.metric("Presupuesto Total", f"S/ {b['presupuesto_estimado']:,.2f}")
                bc2.metric("Proveedor Recomendado", b['proveedor_recomendado'])
                st.info(f"📝 {b['justificacion']}")
                
                with st.expander("🧠 Ver Razonamiento del Agente (Chain of Thought)", expanded=False):
                    st.markdown("El agente `BudgetAgent` procesó la siguiente cadena de pensamiento utilizando los datos recuperados (RAG) y los requerimientos del pedido:")
                    st.markdown(f"> {b.get('razonamiento', 'No se proporcionó razonamiento.')}")

            # Mostrar explicación de aprobación
            if "approval_explanation" in results:
                st.markdown("#### ⚠️ Aprobación Requerida (Human-in-the-Loop)")
                st.warning(results["approval_explanation"])

            st.divider()

            # Botones de aprobación HITL
            st.markdown("### 🤔 ¿Aprueba este presupuesto?")
            col_approve, col_reject = st.columns(2)

            with col_approve:
                if st.button("✅ Aprobar Presupuesto", type="primary", use_container_width=True):
                    with st.spinner("🔄 Procesando compra y notificando producción..."):
                        try:
                            approval_results = st.session_state.orchestrator.handle_budget_approval(
                                approved=True,
                                state=st.session_state.materials_state,
                            )
                            st.session_state.materials_results = {
                                **results,
                                **approval_results,
                            }
                            st.session_state.materials_step = "completed"
                            st.rerun()
                        except Exception as e:
                            st.error(f"⚠️ Error: {e}")

            with col_reject:
                if st.button("❌ Rechazar Presupuesto", use_container_width=True):
                    try:
                        approval_results = st.session_state.orchestrator.handle_budget_approval(
                            approved=False,
                            state=st.session_state.materials_state,
                        )
                        st.session_state.materials_results = {
                            **results,
                            **approval_results,
                        }
                        st.session_state.materials_step = "completed"
                        st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ Error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 3: Resultado final
    # ─────────────────────────────────────────────────────────────────────────
    elif mat_step == "completed":
        results = st.session_state.materials_results

        if results:
            estado = results.get("estado", "desconocido")

            # Mostrar todas las etapas completadas
            st.markdown("#### 📋 Proceso Completado")
            for etapa in results.get("etapas", []):
                if etapa.startswith("⚠️"):
                    st.warning(etapa)
                elif etapa.startswith("🔄"):
                    st.info(etapa)
                else:
                    if "✅" in etapa:
                        st.success(etapa)
                    else:
                        st.markdown(f"- {etapa}")

            st.divider()

            if estado == "completado":
                st.success("✅ **Proceso de compra de materiales completado exitosamente**")

                # Mostrar detalles de la compra
                if "purchase" in results:
                    p = results["purchase"]
                    st.markdown("#### 🛒 Detalles de la Compra")
                    pc1, pc2, pc3 = st.columns(3)
                    pc1.metric("Orden de Compra", p.get("orden_compra_id", "N/A"))
                    pc2.metric("Proveedor", p.get("proveedor", "N/A"))
                    pc3.metric("Monto Total", f"S/ {p.get('monto_total', 0):,.2f}")
                    st.info(f"📅 Fecha estimada de entrega: **{p.get('fecha_entrega', 'N/A')}**")

                # Mostrar notificación
                if "notificacion" in results:
                    n = results["notificacion"]
                    st.markdown("#### 📢 Notificación a Producción")
                    st.success(n.get("mensaje", "Producción notificada"))

            elif estado == "cancelado":
                st.error("❌ **Proceso cancelado — Presupuesto rechazado**")

            st.divider()

            # Botón para reiniciar el proceso
            if st.button("🔄 Nuevo ciclo de compra", use_container_width=True):
                st.session_state.materials_state = SharedState()
                st.session_state.materials_results = None
                st.session_state.materials_step = "idle"
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
