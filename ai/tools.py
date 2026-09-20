from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional

import pandas as pd

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
            "get_channel_margin": self.get_channel_margin,
            "get_break_even_point": self.get_break_even_point,
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

    def get_channel_margin(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Abertura transacional por canal usando diretamente vendas.csv aprovado."""
        try:
            vendas, source = self.context.sales_approved(), self.context.sales_source
        except (FileNotFoundError, ValueError) as exc:
            return {
                "found": False,
                "area": "channel_economics",
                "source": "Data Room/vendas.csv",
                "status": "data_source_unavailable",
                "message": str(exc),
                "dashboard_used": False,
            }

        if "canal" not in vendas.columns:
            vendas["canal"] = "Sem canal"
        vendas["canal"] = vendas["canal"].fillna("Sem canal").replace("", "Sem canal")

        grouped = vendas.groupby("canal", dropna=False).agg(
            receita_bruta=("receita_bruta", "sum"),
            receita_liquida=("receita_liquida", "sum"),
            custo_produto=("custo_produto", "sum"),
            custo_frete=("custo_frete", "sum"),
            margem_contribuicao=("margem_contribuicao", "sum"),
            pedidos_aprovados=("order_id", "nunique"),
            unidades=("quantidade", "sum"),
        ).reset_index()

        grouped["margem_pct"] = grouped.apply(
            lambda r: (r["margem_contribuicao"] / r["receita_liquida"]) if r["receita_liquida"] else 0.0,
            axis=1,
        )

        records = []
        for row in grouped.to_dict("records"):
            records.append({
                "canal": row["canal"],
                "receita_bruta": float(row["receita_bruta"]),
                "receita_liquida": float(row["receita_liquida"]),
                "custo_produto": float(row["custo_produto"]),
                "custo_frete": float(row["custo_frete"]),
                # The case already provides contribution margin after product cost and freight.
                "margem_contribuicao_apos_frete_antes_impostos": float(row["margem_contribuicao"]),
                "margem_pct_apos_frete_antes_impostos": float(row["margem_pct"]),
                "pedidos_aprovados": int(row["pedidos_aprovados"]),
                "unidades": float(row["unidades"]),
            })

        tax_cols = []
        try:
            from .data_source import detect_tax_columns
            tax_cols = detect_tax_columns(vendas)
        except Exception:
            tax_cols = []

        order_by = str(args.get("order_by", "margem_contribuicao_apos_frete_antes_impostos"))
        descending = bool(args.get("descending", True))
        valid = {
            "margem_contribuicao_apos_frete_antes_impostos",
            "margem_pct_apos_frete_antes_impostos",
            "receita_liquida",
            "pedidos_aprovados",
        }
        if order_by not in valid:
            order_by = "margem_contribuicao_apos_frete_antes_impostos"
        records.sort(key=lambda x: x.get(order_by, 0), reverse=descending)

        return {
            "area": "channel_economics",
            "found": bool(records),
            "source": "vendas.csv — universo aprovado",
            "source_path": str(source),
            "status": "validated" if records else "empty",
            "dashboard_used": False,
            "metric_definition": {
                "margem_contribuicao_apos_frete": "campo margem_contribuicao do Data Room, agregado no universo aprovado por canal; representa a contribuição após os custos já incorporados pelo case, incluindo frete, e antes de impostos.",
                "margem_pct_apos_frete": "margem de contribuição / receita líquida do canal.",
            },
            "channels": records,
            "taxes": {
                "available": bool(tax_cols),
                "columns_detected": tax_cols,
                "note": "Não há imposto/alíquota determinísticos no Data Room validado." if not tax_cols else "Campos tributários detectados; revisão da semântica tributária ainda é recomendada antes de chamar o resultado de CM2 pós-impostos.",
            },
            "limitations": [
                "A base de vendas não possui imposto/alíquota determinísticos no schema validado; o resultado é pré-impostos.",
                "Abertura por canal descreve o canal registrado na venda; não é atribuição 1:1 de marketing.",
                "Não subtrair investimento de marketing desta margem.",
            ],
            "governance": {
                "not_net_income": True,
                "not_after_tax": not bool(tax_cols),
                "dashboard_used": False,
            },
            "query_parameters": {"order_by": order_by, "descending": descending},
        }

    def get_break_even_point(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula um limiar indicativo usando vendas reais e valida H5/H8 por faixas de AOV."""
        try:
            vendas, source = self.context.sales_approved(), self.context.sales_source
        except (FileNotFoundError, ValueError) as exc:
            return {
                "found": False,
                "area": "break_even",
                "source": "Data Room/vendas.csv",
                "status": "data_source_unavailable",
                "message": str(exc),
                "dashboard_used": False,
            }

        if "receita_liquida" not in vendas.columns or "custo_frete" not in vendas.columns or "margem_contribuicao" not in vendas.columns:
            return {
                "found": False,
                "area": "break_even",
                "status": "invalid_data",
                "message": "A base validada não possui receita_liquida, custo_frete e margem_contribuicao para o cálculo.",
            }

        order_agg = vendas.groupby("order_id", dropna=False).agg(
            receita_liquida=("receita_liquida", "sum"),
            custo_frete=("custo_frete", "sum"),
            margem_contribuicao=("margem_contribuicao", "sum"),
            quantidade=("quantidade", "sum"),
        ).reset_index()
        order_agg = order_agg[order_agg["receita_liquida"] > 0].copy()
        order_agg["contribuicao_pre_frete"] = order_agg["margem_contribuicao"] + order_agg["custo_frete"]
        total_revenue = float(order_agg["receita_liquida"].sum())
        pre_freight_rate = float(order_agg["contribuicao_pre_frete"].sum() / total_revenue) if total_revenue else 0.0
        avg_freight = float(order_agg["custo_frete"].mean()) if len(order_agg) else 0.0
        current_aov = float(total_revenue / len(order_agg)) if len(order_agg) else 0.0
        indicative_aov = float(avg_freight / pre_freight_rate) if pre_freight_rate > 0 else 0.0

        bins = [-float("inf"), 100, 250, 500, 750, 1000, 1500, float("inf")]
        labels = ["< R$100", "R$100–249", "R$250–499", "R$500–749", "R$750–999", "R$1.000–1.499", "R$1.500+"]
        order_agg["faixa_aov"] = pd.cut(order_agg["receita_liquida"], bins=bins, labels=labels, right=False)
        order_agg["frete_pct_aov"] = order_agg["custo_frete"] / order_agg["receita_liquida"].replace(0, pd.NA)
        order_agg["margem_negativa"] = order_agg["margem_contribuicao"] < 0

        band = order_agg.groupby("faixa_aov", observed=False).agg(
            pedidos=("order_id", "count"),
            aov_medio=("receita_liquida", "mean"),
            frete_medio=("custo_frete", "mean"),
            taxa_margem_negativa=("margem_negativa", "mean"),
            frete_pct_medio=("frete_pct_aov", "mean"),
        ).reset_index()
        band_records = [
            {
                "faixa_aov": str(r["faixa_aov"]),
                "pedidos": int(r["pedidos"]),
                "aov_medio": float(r["aov_medio"]),
                "frete_medio": float(r["frete_medio"]),
                "taxa_margem_negativa": float(r["taxa_margem_negativa"]),
                "frete_pct_medio": float(r["frete_pct_medio"]) if pd.notna(r["frete_pct_medio"]) else 0.0,
            }
            for r in band.to_dict("records")
            if int(r["pedidos"]) > 0
        ]

        category = args.get("categoria")
        category_sensitivity = []
        if "categoria" in vendas.columns:
            for cat, group in vendas.groupby("categoria", dropna=False):
                cat_orders = group.groupby("order_id", dropna=False).agg(
                    receita_liquida=("receita_liquida", "sum"),
                    custo_frete=("custo_frete", "sum"),
                    margem_contribuicao=("margem_contribuicao", "sum"),
                ).reset_index()
                cat_orders = cat_orders[cat_orders["receita_liquida"] > 0]
                if cat_orders.empty:
                    continue
                cat_pre_rate = float((cat_orders["margem_contribuicao"] + cat_orders["custo_frete"]).sum() / cat_orders["receita_liquida"].sum())
                cat_frete = float(cat_orders["custo_frete"].mean())
                category_sensitivity.append({
                    "categoria": str(cat) if pd.notna(cat) else "Sem categoria",
                    "pedidos": int(len(cat_orders)),
                    "frete_medio": cat_frete,
                    "taxa_contribuicao_pre_frete": cat_pre_rate,
                    "aov_break_even_indicativo": float(cat_frete / cat_pre_rate) if cat_pre_rate > 0 else 0.0,
                })

        selected_category = None
        if category:
            selected_category = next((x for x in category_sensitivity if x["categoria"].lower() == str(category).lower()), None)
            if selected_category is None:
                return {
                    "found": False,
                    "area": "break_even",
                    "source": "vendas.csv — universo aprovado",
                    "status": "category_not_found",
                    "dashboard_used": False,
                    "query_parameters": {"categoria": category},
                }

        negative_orders = order_agg[order_agg["margem_negativa"]]
        result = {
            "aov_break_even_indicativo": indicative_aov,
            "aov_atual_medio": current_aov,
            "frete_medio": avg_freight,
            "taxa_contribuicao_pre_frete": pre_freight_rate,
            "pedidos_analisados": int(len(order_agg)),
            "pedidos_margem_negativa": int(len(negative_orders)),
            "taxa_margem_negativa": float(len(negative_orders) / len(order_agg)) if len(order_agg) else 0.0,
            "pedidos_abaixo_aov_indicativo": int((order_agg["receita_liquida"] < indicative_aov).sum()) if indicative_aov > 0 else 0,
            "taxa_abaixo_aov_indicativo": float((order_agg["receita_liquida"] < indicative_aov).mean()) if indicative_aov > 0 and len(order_agg) else 0.0,
        }
        if selected_category:
            result = selected_category

        return {
            "found": True,
            "area": "break_even",
            "source": "vendas.csv — universo aprovado",
            "source_path": str(source),
            "status": "validated_indicative",
            "dashboard_used": False,
            "inputs": {
                "aov_atual_medio": current_aov,
                "frete_medio": avg_freight,
                "taxa_contribuicao_pre_frete": pre_freight_rate,
            },
            "method": {
                "formula": "AOV_break_even_indicativo = frete_medio_do_pedido / taxa_de_contribuicao_pre_frete_agregada",
                "definition": "Limiar indicativo: valor de receita líquida de um pedido no qual a taxa de contribuição pré-frete agregada consegue absorver o frete médio observado.",
                "order_level_validation": "A base também é segmentada por faixas de AOV para observar taxa real de margem negativa e peso médio do frete.",
            },
            "result": result,
            "category_sensitivity": category_sensitivity,
            "aov_band_analysis": band_records,
            "negative_margin_reference": {
                "frete_medio_pedidos_margem_negativa": float(negative_orders["custo_frete"].mean()) if len(negative_orders) else 0.0,
                "frete_medio_demais_pedidos": float(order_agg.loc[~order_agg["margem_negativa"], "custo_frete"].mean()) if len(order_agg.loc[~order_agg["margem_negativa"]]) else 0.0,
            },
            "limitations": [
                "Não há imposto/alíquota no Data Room validado; o limiar não representa CM2 pós-impostos.",
                "Frete varia por pedido; R$ do break-even é um limiar indicativo, não uma regra universal de checkout.",
                "Não modela elasticidade de demanda, conversão ou alteração do mix ao elevar o AOV mínimo.",
                "A validação operacional deve observar faixas de AOV e perfil de frete, não apenas a média global.",
            ],
            "query_parameters": {"categoria": category},
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

    @tool("get_channel_margin")
    def get_channel_margin(
        order_by: Literal["margem_contribuicao_apos_frete_antes_impostos", "margem_pct_apos_frete_antes_impostos", "receita_liquida", "pedidos_aprovados"] = "margem_contribuicao_apos_frete_antes_impostos",
        descending: bool = True,
    ) -> str:
        return json.dumps(
            registry.execute("get_channel_margin", {"order_by": order_by, "descending": descending}).result,
            ensure_ascii=False,
        )

    @tool("get_break_even_point")
    def get_break_even_point(categoria: str = "") -> str:
        return json.dumps(
            registry.execute("get_break_even_point", {"categoria": categoria or None}).result,
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
        get_channel_margin,
        get_break_even_point,
    ]
