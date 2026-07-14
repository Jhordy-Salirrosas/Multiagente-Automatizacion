"""Tests para el proceso de aprobación humana (HITL)."""
import pytest
from core.shared_state import SharedState, ConversationStage
from core.mcp_messages import BudgetResult, MaterialPlan
from agents.approval_agent import ApprovalAgent

def test_approval_agent_prepare():
    """Verifica que el agente prepara el texto para HITL correctamente."""
    agent = ApprovalAgent()
    state = SharedState()
    
    state.material_plan = MaterialPlan(
        pedido_id="BATCH-TEST",
        materiales=["tela algodón"],
        cantidades=[100]
    )
    state.budget_result = BudgetResult(
        presupuesto_estimado=1500.0,
        proveedor_recomendado="Proveedor Test",
        justificacion="Historial favorable"
    )
    
    explicacion = agent.prepare_approval(state)
    
    assert "1,500" in explicacion or "1500" in explicacion
    assert "tela" in explicacion.lower()
    assert "Proveedor" in explicacion or "Textiles" in explicacion

def test_approval_agent_process_approved():
    """Verifica que se actualice el estado cuando HITL aprueba."""
    agent = ApprovalAgent()
    state = SharedState()
    state.budget_result = BudgetResult(
        presupuesto_estimado=1500.0,
        proveedor_recomendado="Test",
        estado="Pendiente"
    )
    
    agent.process_decision(approved=True, state=state)
    assert state.budget_result.estado == "Aprobado"

def test_approval_agent_process_rejected():
    """Verifica que se actualice el estado cuando HITL rechaza."""
    agent = ApprovalAgent()
    state = SharedState()
    state.budget_result = BudgetResult(
        presupuesto_estimado=1500.0,
        proveedor_recomendado="Test",
        estado="Pendiente"
    )
    
    agent.process_decision(approved=False, state=state)
    assert state.budget_result.estado == "Rechazado"
