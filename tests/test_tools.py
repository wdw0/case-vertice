from pathlib import Path

from ai.context import ContextStore
from ai.tools import ToolRegistry

CONTEXT = Path(__file__).resolve().parents[1] / "data" / "vertice_ai_context.json"
DATA_ROOM = Path(__file__).resolve().parent / "fixtures" / "data_room"


def test_registry_tool_names():
    registry = ToolRegistry(ContextStore(CONTEXT))
    assert registry.names() == [
        "get_margin_opportunities",
        "get_marketing_efficiency",
        "get_inventory_opportunities",
        "get_support_opportunities",
        "get_prioritized_opportunities",
        "get_opportunity_by_id",
        "get_product_details",
        "get_product_ranking",
        "get_channel_margin",
        "get_break_even_point",
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



def test_product_detail_resolves_name_and_rankings():
    registry = ToolRegistry(ContextStore(CONTEXT))
    result = registry.execute(
        "get_product_details",
        {"query": "O que vc tem a dizer sobre o item Calça Jeans Moderno Nude"},
    ).result
    assert result["found"] is True
    assert result["product"]["sku_id"] == "SKU-04174"
    assert result["product"]["rank_rentabilidade"] == 1
    assert result["product"]["rentabilidade"] > 0.67


def test_product_ranking_returns_rentability_leader():
    registry = ToolRegistry(ContextStore(CONTEXT))
    result = registry.execute(
        "get_product_ranking",
        {"order_by": "rentabilidade", "descending": True, "limit": 3},
    ).result
    assert result["ranking"][0]["sku_id"] == "SKU-04174"
    assert result["ranking"][0]["produto"] == "Calça Jeans Moderno Nude"
    assert round(result["ranking"][0]["rentabilidade"] * 100, 2) == 67.79


def test_channel_margin_uses_direct_data_room_and_is_pre_tax():
    context = ContextStore(CONTEXT, data_room_path=DATA_ROOM)
    registry = ToolRegistry(context)
    result = registry.execute("get_channel_margin").result
    assert result["found"] is True
    assert result["dashboard_used"] is False
    assert result["taxes"]["available"] is False
    assert result["source"] == "vendas.csv — universo aprovado"
    assert {x["canal"] for x in result["channels"]} == {"Google Ads", "Marketplace"}
    google = next(x for x in result["channels"] if x["canal"] == "Google Ads")
    assert round(google["margem_contribuicao_apos_frete_antes_impostos"], 2) == 150.00


def test_break_even_uses_direct_sales_and_validates_aov_bands():
    context = ContextStore(CONTEXT, data_room_path=DATA_ROOM)
    registry = ToolRegistry(context)
    result = registry.execute("get_break_even_point").result
    assert result["found"] is True
    assert result["dashboard_used"] is False
    assert result["source"] == "vendas.csv — universo aprovado"
    assert result["status"] == "validated_indicative"
    assert result["result"]["aov_break_even_indicativo"] > 0
    assert result["aov_band_analysis"]
    assert result["result"]["pedidos_margem_negativa"] == 1


def test_break_even_supports_direct_category_sensitivity():
    context = ContextStore(CONTEXT, data_room_path=DATA_ROOM)
    registry = ToolRegistry(context)
    result = registry.execute("get_break_even_point", {"categoria": "Moda"}).result
    assert result["found"] is True
    assert result["result"]["categoria"] == "Moda"
    assert result["result"]["aov_break_even_indicativo"] > 0
