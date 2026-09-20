from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional

from .context import ContextStore


@dataclass(frozen=True)
class ToolExecution:
    name: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]


class ToolRegistry:
    """Ferramentas determinísticas apoiadas exclusivamente no contexto auditado."""

    def __init__(self, context: ContextStore):
        self.context = context
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "get_margin_opportunities": self.get_margin_opportunities,
            "get_marketing_efficiency": self.get_marketing_efficiency,
            "get_inventory_opportunities": self.get_inventory_opportunities,
            "get_support_opportunities": self.get_support_opportunities,
            "get_prioritized_opportunities": self.get_prioritized_opportunities,
            "get_opportunity_by_id": self.get_opportunity_by_id,
            "get_product_details": self.get_product_details,
            "get_product_ranking": self.get_product_ranking,
        }

    def execute(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> ToolExecution:
        arguments = arguments or {}
        if name not in self._handlers:
            raise KeyError(f"Tool desconhecida: {name}")
        return ToolExecution(name=name, arguments=arguments, result=self._handlers[name](arguments))

    def names(self) -> List[str]:
        return list(self._handlers)

    def get_margin_opportunities(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "area": "margin",
            "kpis": self.context.kpis["margem"],
            "opportunities": self.context.opportunities_by_area("margin"),
            "definitions": {
                "margem_pre_devolucao": "margem de contribuição antes do efeito econômico das devoluções",
                "margem_pos_devolucao_receita_original": "margem pós-devolução sobre a receita originalmente vendida",
                "margem_pos_devolucao_receita_retida": "margem pós-devolução sobre a receita efetivamente retida",
            },
            "governance": {
                "confidence_and_limitations_required": True,
                "note": "Devoluções usam premissa estimada de frete reverso espelhado.",
            },
        }

    def get_marketing_efficiency(self, args: Dict[str, Any]) -> Dict[str, Any]:
        opportunities = self.context.opportunities_by_area("marketing")
        order_by = args.get("order_by", "roas")
        descending = bool(args.get("descending", True))
        views = self.context.data.get("analysis_views", {})
        channels = list(views.get("marketing_channels") or [])
        if order_by not in {"roas", "cac", "investimento", "receita"}:
            order_by = "roas"
        channels.sort(key=lambda x: x.get(order_by, 0), reverse=descending)
        return {
            "area": "marketing",
            "source_of_truth": "marketing.csv / camada analítica determinística",
            "metric_definition": {
                "roas": "receita_gerada_total / investimento_total",
                "cac": "investimento_total / conversoes_total",
            },
            "kpis": self.context.kpis["marketing"],
            "channels": channels,
            "opportunities": opportunities,
            "limitations": [
                "Marketing e vendas não possuem correspondência determinística 1:1 por cliente/pedido.",
                "Não permite afirmar margem líquida real ou LTV por canal.",
                "Decisões de orçamento devem ser validadas via teste incremental e retorno marginal.",
            ],
            "query_parameters": {"order_by": order_by, "descending": descending},
        }

    def get_inventory_opportunities(self, args: Dict[str, Any]) -> Dict[str, Any]:
        limit = int(args.get("limit", 10))
        limit = max(1, min(50, limit))
        stockout_order_by = str(args.get("stockout_order_by", "unidades_vendidas"))
        coverage_order_by = str(args.get("coverage_order_by", "capital_exposicao"))
        views = self.context.data.get("analysis_views", {})

        stockouts = list(views.get("inventory_stockouts_high_demand") or [])
        coverage = list(views.get("inventory_high_coverage") or [])
        categoria = args.get("categoria")
        sku_id = str(args.get("sku_id", "")).upper() or None
        if categoria:
            stockouts = [x for x in stockouts if str(x.get("categoria", "")).lower() == str(categoria).lower()]
            coverage = [x for x in coverage if str(x.get("categoria", "")).lower() == str(categoria).lower()]
        if sku_id:
            stockouts = [x for x in stockouts if str(x.get("sku_id", "")).upper() == sku_id]
            coverage = [x for x in coverage if str(x.get("sku_id", "")).upper() == sku_id]
        valid_stock_fields = {"unidades_vendidas", "receita_historica", "margem_historica", "lead_time_reposicao", "receita_potencial_bloqueada_estimada"}
        valid_coverage_fields = {"capital_exposicao", "cobertura_teorica_dias", "estoque_disponivel", "unidades_vendidas"}
        if stockout_order_by not in valid_stock_fields:
            stockout_order_by = "unidades_vendidas"
        if coverage_order_by not in valid_coverage_fields:
            coverage_order_by = "capital_exposicao"

        stockouts.sort(key=lambda x: x.get(stockout_order_by, 0), reverse=True)
        coverage.sort(key=lambda x: x.get(coverage_order_by, 0), reverse=True)
        return {
            "area": "inventory",
            "kpis": self.context.kpis["estoque"],
            "opportunities": self.context.opportunities_by_area("inventory"),
            "stockouts_high_demand": stockouts[:limit],
            "high_coverage": coverage[:limit],
            "stockout_semantics": {
                "realized_loss_available_by_sku": False,
                "preferred_impact_metric": "receita_potencial_bloqueada_estimada",
                "preferred_impact_label": "receita potencial bloqueada estimada durante o lead time",
                "historical_fields": ["receita_historica", "margem_historica"],
                "warning": "Não chamar receita histórica ou margem histórica de prejuízo causado pela ruptura.",
            },
            "coverage_semantics": {
                "is_theoretical": True,
                "label": "exposição potencial de capital associada ao custo do estoque",
                "warning": "Não chamar capital_exposicao de capital perdido/parado nem afirmar overstock garantido.",
            },
            "query_parameters": {
                "limit": limit,
                "stockout_order_by": stockout_order_by,
                "coverage_order_by": coverage_order_by,
                "categoria": categoria,
                "sku_id": sku_id,
            },
            "limitations": [
                "Estoque é snapshot; cobertura é teórica e usa histórico de vendas.",
                "Demanda futura pode variar por sazonalidade e campanhas.",
                "Ruptura por SKU não possui perda realizada observada; receita potencial bloqueada é uma estimativa durante o lead time.",
            ],
        }

    def get_support_opportunities(self, args: Dict[str, Any]) -> Dict[str, Any]:
        limit = int(args.get("limit", 10))
        limit = max(1, min(20, limit))
        views = self.context.data.get("analysis_views", {})
        return {
            "area": "support",
            "kpis": self.context.kpis["atendimento"],
            "opportunities": self.context.opportunities_by_area("support"),
            "top_customers": self.context.limited_view(views.get("support_top_customers") or [], limit=limit),
            "limitations": [
                "Concentração de tickets é evidência de concentração de demanda/fricção, não prova de churn individual.",
                "Risco individual de churn requer classificação/validação posterior de NLP.",
            ],
        }


    def get_product_details(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or "").strip()
        sku_id = args.get("sku_id")
        product = self.context.product_by_sku(str(sku_id)) if sku_id else None
        matches = [product] if product else self.context.find_products(query, limit=5)

        if not matches:
            return {
                "found": False,
                "area": "product",
                "query": query,
                "message": "Produto ou SKU não encontrado no contexto estruturado de produtos.",
                "source_of_truth": self.context.product_analytics.get("source"),
            }

        product = matches[0]
        return {
            "found": True,
            "area": "product",
            "source_of_truth": self.context.product_analytics.get("source"),
            "product": product,
            "rankings": {
                "rentabilidade": product.get("rank_rentabilidade"),
                "faturamento": product.get("rank_faturamento"),
                "margem": product.get("rank_margem"),
                "unidades": product.get("rank_unidades"),
            },
            "metric_definitions": {
                "faturamento": "soma da receita líquida do SKU",
                "margem": "soma da margem de contribuição do SKU",
                "rentabilidade": "margem / receita bruta do SKU",
                "unidades": "soma da quantidade vendida do SKU",
            },
            "inventory_note": "Estoque e atributos de estoque vêm de estoque.csv e representam um snapshot; não são parte do cálculo da rentabilidade histórica.",
            "limitations": [
                "Rentabilidade é uma métrica histórica agregada sobre as vendas observadas; não mede demanda futura ou causalidade de marketing.",
                "A posição no ranking é relativa à população de SKUs com receita_bruta > 0 no contexto estruturado.",
                "Estoque é snapshot e deve ser interpretado separadamente da janela histórica de vendas.",
            ],
            "query_parameters": {"query": query, "sku_id": sku_id},
        }

    def get_product_ranking(self, args: Dict[str, Any]) -> Dict[str, Any]:
        order_by = str(args.get("order_by", "rentabilidade"))
        descending = bool(args.get("descending", True))
        limit = int(args.get("limit", 10))
        limit = max(1, min(50, limit))
        valid = {"rentabilidade", "faturamento", "margem", "unidades"}
        if order_by not in valid:
            order_by = "rentabilidade"
        products = list(self.context.products)
        products.sort(
            key=lambda x: (x.get(order_by, float("-inf")), x.get("faturamento", float("-inf"))),
            reverse=descending,
        )
        ranking = []
        for position, product in enumerate(products[:limit], start=1):
            ranking.append({
                "posicao_consulta": position,
                "sku_id": product.get("sku_id"),
                "produto": product.get("produto"),
                "faturamento": product.get("faturamento"),
                "margem": product.get("margem"),
                "receita_bruta": product.get("receita_bruta"),
                "unidades": product.get("unidades"),
                "rentabilidade": product.get("rentabilidade"),
                "rank_rentabilidade": product.get("rank_rentabilidade"),
            })
        return {
            "area": "product",
            "source_of_truth": self.context.product_analytics.get("source"),
            "population_definition": self.context.product_analytics.get("population_definition"),
            "metric_definition": self.context.product_analytics.get("sales_aggregation"),
            "ranking": ranking,
            "query_parameters": {
                "order_by": order_by,
                "descending": descending,
                "limit": limit,
            },
            "limitations": [
                "Ranking de rentabilidade é histórico e descritivo; não representa previsão de vendas futuras.",
                "Em empate, a ordenação usa faturamento como desempate para manter determinismo.",
            ],
        }

    def get_prioritized_opportunities(self, _: Dict[str, Any]) -> Dict[str, Any]:
        portfolio = []
        by_id = {o.get("id"): o for o in self.context.opportunities}
        for item in self.context.prioritized():
            merged = dict(item)
            detail = by_id.get(item.get("id"))
            if detail:
                for key in ("title", "metric", "evidence", "notes", "limitations", "source"):
                    if key not in merged and key in detail:
                        merged[key] = detail[key]
            portfolio.append(merged)
        return {
            "portfolio": portfolio,
            "method": {
                "type": "MCDA",
                "weights": {
                    "impact": 0.30,
                    "speed": 0.25,
                    "effort": 0.20,
                    "risk": 0.10,
                    "confidence": "multiplicador: high=1.0, medium=0.75, low=0.40",
                },
                "authority": "Opportunity Engine da Etapa 1",
                "ranking_locked": True,
            },
        }

    def get_opportunity_by_id(self, args: Dict[str, Any]) -> Dict[str, Any]:
        opportunity_id = args.get("id")
        if not opportunity_id:
            raise ValueError("O parâmetro 'id' é obrigatório.")
        opportunity = self.context.opportunity_by_id(str(opportunity_id))
        if not opportunity:
            return {"found": False, "id": opportunity_id, "message": "Oportunidade não encontrada no contexto estruturado."}
        portfolio = next((x for x in self.context.priority_portfolio if x.get("id") == opportunity_id), None)
        return {"found": True, "opportunity": opportunity, "priority": portfolio}


# Mantido para compatibilidade com versões anteriores. O VerticeAgent atual não usa tool-calling do LLM.
def build_langchain_tools(registry: ToolRegistry) -> List[Any]:
    from langchain_core.tools import tool

    @tool("get_margin_opportunities")
    def get_margin_opportunities() -> str:
        return json.dumps(registry.execute("get_margin_opportunities").result, ensure_ascii=False)

    @tool("get_marketing_efficiency")
    def get_marketing_efficiency(
        order_by: Literal["roas", "cac", "investimento", "receita"] = "roas",
        descending: bool = True,
    ) -> str:
        return json.dumps(
            registry.execute("get_marketing_efficiency", {"order_by": order_by, "descending": descending}).result,
            ensure_ascii=False,
        )

    @tool("get_inventory_opportunities")
    def get_inventory_opportunities(limit: int = 10) -> str:
        return json.dumps(registry.execute("get_inventory_opportunities", {"limit": limit}).result, ensure_ascii=False)

    @tool("get_support_opportunities")
    def get_support_opportunities(limit: int = 10) -> str:
        return json.dumps(registry.execute("get_support_opportunities", {"limit": limit}).result, ensure_ascii=False)

    @tool("get_prioritized_opportunities")
    def get_prioritized_opportunities() -> str:
        return json.dumps(registry.execute("get_prioritized_opportunities").result, ensure_ascii=False)

    @tool("get_opportunity_by_id")
    def get_opportunity_by_id(id: str) -> str:
        return json.dumps(registry.execute("get_opportunity_by_id", {"id": id}).result, ensure_ascii=False)

    @tool("get_product_details")
    def get_product_details(query: str, sku_id: str = "") -> str:
        return json.dumps(
            registry.execute("get_product_details", {"query": query, "sku_id": sku_id or None}).result,
            ensure_ascii=False,
        )

    @tool("get_product_ranking")
    def get_product_ranking(
        order_by: Literal["rentabilidade", "faturamento", "margem", "unidades"] = "rentabilidade",
        descending: bool = True,
        limit: int = 10,
    ) -> str:
        return json.dumps(
            registry.execute(
                "get_product_ranking",
                {"order_by": order_by, "descending": descending, "limit": limit},
            ).result,
            ensure_ascii=False,
        )

    return [
        get_margin_opportunities,
        get_marketing_efficiency,
        get_inventory_opportunities,
        get_support_opportunities,
        get_prioritized_opportunities,
        get_opportunity_by_id,
        get_product_details,
        get_product_ranking,
    ]
