from pathlib import Path

from ai.context import ContextStore
from ai.tools import ToolRegistry

CONTEXT = Path(__file__).resolve().parents[1] / "data" / "vertice_ai_context.json"


def test_registry_tool_names():
    registry = ToolRegistry(ContextStore(CONTEXT))
    assert registry.names() == [
        "get_margin_opportunities",
        "get_marketing_efficiency",
        "get_inventory_opportunities",
        "get_support_opportunities",
        "get_prioritized_opportunities",
        "get_opportunity_by_id",
    ]


def test_margin_tool_has_opportunities():
    registry = ToolRegistry(ContextStore(CONTEXT))
    result = registry.execute("get_margin_opportunities").result
    assert result["area"] == "margin"
    assert result["opportunities"]


def test_priority_tool_preserves_engine_authority():
    registry = ToolRegistry(ContextStore(CONTEXT))
    result = registry.execute("get_prioritized_opportunities").result
    assert result["method"]["authority"] == "Opportunity Engine da Etapa 1"
    assert result["method"]["ranking_locked"] is True
    assert result["portfolio"]


def test_opportunity_detail_not_found_is_explicit():
    registry = ToolRegistry(ContextStore(CONTEXT))
    result = registry.execute("get_opportunity_by_id", {"id": "OPP-NAO-EXISTE"}).result
    assert result["found"] is False


def test_inventory_semantics_are_explicit():
    registry = ToolRegistry(ContextStore(CONTEXT))
    result = registry.execute(
        "get_inventory_opportunities",
        {"limit": 3, "stockout_order_by": "receita_potencial_bloqueada_estimada"},
    ).result
    assert result["stockout_semantics"]["realized_loss_available_by_sku"] is False
    assert result["stockouts_high_demand"]
    assert "receita_potencial_bloqueada_estimada" in result["stockouts_high_demand"][0]
    assert result["coverage_semantics"]["is_theoretical"] is True

