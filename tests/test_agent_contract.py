from pathlib import Path

from ai.context import ContextStore

CONTEXT = Path(__file__).resolve().parents[1] / "data" / "vertice_ai_context.json"


def test_context_is_the_structured_agent_contract():
    ctx = ContextStore(CONTEXT)
    assert ctx.data["source"]["primary"] == "Data Room CSV + camada analítica determinística Python"
    assert ctx.data["source"]["dashboard_json_status"] == "requires_review"
    assert ctx.data["opportunities"]
    assert ctx.data["priority_portfolio"]
