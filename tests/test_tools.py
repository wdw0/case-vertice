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
    assert result["portfolio"]


def test_opportunity_detail_not_found_is_explicit():
    registry = ToolRegistry(ContextStore(CONTEXT))
    result = registry.execute("get_opportunity_by_id", {"id": "OPP-NAO-EXISTE"}).result
    assert result["found"] is False
