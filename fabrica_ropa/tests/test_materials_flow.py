"""Tests del flujo de materiales (Proceso 2)."""
import pytest
from core.shared_state import SharedState, ConversationStage
from core.mcp_messages import MaterialPlan
from agents.orchestrator import Orchestrator

def test_handle_materials_purchase_initialization():
    """Verifica que el orquestador inicie correctamente el flujo de compra."""
    o = Orchestrator()
    state = SharedState()
    
    # Simular ejecución hasta HITL
    results = o.handle_materials_purchase(state)
    
    assert "etapas" in results
    assert len(results["etapas"]) == 3
    assert "material_plan" in results
    assert "budget" in results
    assert "approval_explanation" in results
    assert state.stage == ConversationStage.WAITING_BUDGET_APPROVAL

def test_handle_budget_approval_approved():
    """Verifica el flujo cuando el presupuesto es aprobado."""
    o = Orchestrator()
    state = SharedState()
    
    # Setup mock data needed for approval
    state.material_plan = MaterialPlan(
        pedido_id="BATCH-TEST",
        materiales=["tela algodón"],
        cantidades=[100]
    )
    from core.mcp_messages import BudgetResult
    state.budget_result = BudgetResult(
        presupuesto_estimado=1500.0,
        proveedor_recomendado="Textiles del Norte SAC",
        estado="Pendiente",
        justificacion="Test budget"
    )
    
    results = o.handle_budget_approval(approved=True, state=state)
    
    assert results.get("estado") == "completado"
    assert "purchase" in results
    assert "notificacion" in results
    assert state.stage == ConversationStage.PURCHASE_COMPLETE
    assert state.budget_result.estado == "Aprobado"

def test_handle_budget_approval_rejected():
    """Verifica el flujo cuando el presupuesto es rechazado."""
    o = Orchestrator()
    state = SharedState()
    
    # Setup mock data needed for approval
    from core.mcp_messages import BudgetResult
    state.budget_result = BudgetResult(
        presupuesto_estimado=1500.0,
        proveedor_recomendado="Textiles del Norte SAC",
        estado="Pendiente"
    )
    
    results = o.handle_budget_approval(approved=False, state=state)
    
    assert results.get("estado") == "cancelado"
    assert "purchase" not in results
    assert state.stage == ConversationStage.PURCHASE_COMPLETE
    assert state.budget_result.estado == "Rechazado"
