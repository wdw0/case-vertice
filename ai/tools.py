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
    """Deterministic business tools backed only by the structured AI context."""

    def __init__(self, context: ContextStore):
        self.context = context
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "get_margin_opportunities": self.get_margin_opportunities,
            "get_marketing_efficiency": self.get_marketing_efficiency,
            "get_inventory_opportunities": self.get_inventory_opportunities,
            "get_support_opportunities": self.get_support_opportunities,
            "get_prioritized_opportunities": self.get_prioritized_opportunities,
            "get_opportunity_by_id": self.get_opportunity_by_id,
        }

    def execute(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> ToolExecution:
        arguments = arguments or {}
        if name not in self._handlers:
            raise KeyError(f"Tool desconhecida: {name}")
        result = self._handlers[name](arguments)
        return ToolExecution(name=name, arguments=arguments, result=result)

    def names(self) -> List[str]:
        return list(self._handlers)

    def get_margin_opportunities(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "area": "margin",
            "kpis": self.context.kpis["margem"],
            "opportunities": self.context.opportunities_by_area("margin"),
            "governance": {
                "confidence_and_limitations_required": True,
                "note": "Devoluções usam premissa estimada de frete reverso espelhado.",
            },
        }

    def get_marketing_efficiency(self, args: Dict[str, Any]) -> Dict[str, Any]:
        opportunities = self.context.opportunities_by_area("marketing")
        payload: Dict[str, Any] = {
            "area": "marketing",
            "kpis": self.context.kpis["marketing"],
            "opportunities": opportunities,
            "available_detail": False,
            "limitations": [
                "Marketing e vendas não possuem correspondência determinística 1:1 por cliente/pedido.",
                "Decisões de orçamento devem ser validadas via teste incremental e retorno marginal.",
            ],
        }
        views = self.context.data.get("analysis_views", {})
        channels = views.get("marketing_channels")
        if channels:
            payload["available_detail"] = True
            order = args.get("order_by", "roas")
            descending = bool(args.get("descending", True))
            if order in {"roas", "cac", "investimento", "receita"}:
                payload["channels"] = sorted(
                    channels,
                    key=lambda x: x.get(order, 0),
                    reverse=descending,
                )
            else:
                payload["channels"] = channels
        return payload

    def get_inventory_opportunities(self, args: Dict[str, Any]) -> Dict[str, Any]:
        limit = int(args.get("limit", 10))
        limit = max(1, min(50, limit))
        payload: Dict[str, Any] = {
            "area": "inventory",
            "kpis": self.context.kpis["estoque"],
            "opportunities": self.context.opportunities_by_area("inventory"),
            "limitations": [
                "Estoque é snapshot; cobertura é teórica e usa histórico de vendas.",
                "Demanda futura pode variar por sazonalidade e campanhas.",
            ],
        }
        views = self.context.data.get("analysis_views", {})
        if views.get("inventory_stockouts_high_demand"):
            payload["stockouts_high_demand"] = self.context.limited_view(
                views["inventory_stockouts_high_demand"], limit=limit
            )
        if views.get("inventory_high_coverage"):
            payload["high_coverage"] = self.context.limited_view(
                views["inventory_high_coverage"], limit=limit
            )
        return payload

    def get_support_opportunities(self, args: Dict[str, Any]) -> Dict[str, Any]:
        limit = int(args.get("limit", 10))
        limit = max(1, min(20, limit))
        payload: Dict[str, Any] = {
            "area": "support",
            "kpis": self.context.kpis["atendimento"],
            "opportunities": self.context.opportunities_by_area("support"),
            "limitations": [
                "Concentração de tickets é evidência de concentração de demanda/fricção, não prova de churn individual.",
                "Risco individual de churn requer classificador/validação posterior de NLP.",
            ],
        }
        views = self.context.data.get("analysis_views", {})
        if views.get("support_top_customers"):
            payload["top_customers"] = self.context.limited_view(
                views["support_top_customers"], limit=limit
            )
        return payload

    def get_prioritized_opportunities(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "portfolio": self.context.prioritized(),
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
            },
        }

    def get_opportunity_by_id(self, args: Dict[str, Any]) -> Dict[str, Any]:
        opportunity_id = args.get("id")
        if not opportunity_id:
            raise ValueError("O parâmetro 'id' é obrigatório.")
        opportunity = self.context.opportunity_by_id(str(opportunity_id))
        if not opportunity:
            return {
                "found": False,
                "id": opportunity_id,
                "message": "Oportunidade não encontrada no contexto estruturado.",
            }
        portfolio = next(
            (x for x in self.context.priority_portfolio if x.get("id") == opportunity_id),
            None,
        )
        return {
            "found": True,
            "opportunity": opportunity,
            "priority": portfolio,
        }


def build_langchain_tools(registry: ToolRegistry) -> List[Any]:
    """Expose the deterministic registry through LangChain tools for ChatLiteLLM.bind_tools()."""
    from langchain_core.tools import tool

    @tool("get_margin_opportunities")
    def get_margin_opportunities() -> str:
        """Consulta oportunidades, KPIs e evidências validadas da frente de margem."""
        execution = registry.execute("get_margin_opportunities")
        return json.dumps(execution.result, ensure_ascii=False)

    @tool("get_marketing_efficiency")
    def get_marketing_efficiency(
        order_by: Literal["roas", "cac", "investimento", "receita"] = "roas",
        descending: bool = True,
    ) -> str:
        """Consulta eficiência de aquisição por CAC/ROAS e, quando disponível, a visão estruturada por canal."""
        execution = registry.execute(
            "get_marketing_efficiency",
            {"order_by": order_by, "descending": descending},
        )
        return json.dumps(execution.result, ensure_ascii=False)

    @tool("get_inventory_opportunities")
    def get_inventory_opportunities(limit: int = 10) -> str:
        """Consulta rupturas de alta demanda e potencial excesso de estoque."""
        execution = registry.execute("get_inventory_opportunities", {"limit": limit})
        return json.dumps(execution.result, ensure_ascii=False)

    @tool("get_support_opportunities")
    def get_support_opportunities(limit: int = 10) -> str:
        """Consulta oportunidades de atendimento, incluindo WISMO e concentração de demanda."""
        execution = registry.execute("get_support_opportunities", {"limit": limit})
        return json.dumps(execution.result, ensure_ascii=False)

    @tool("get_prioritized_opportunities")
    def get_prioritized_opportunities() -> str:
        """Retorna o portfólio oficial já priorizado pelo Opportunity Engine da Etapa 1."""
        execution = registry.execute("get_prioritized_opportunities")
        return json.dumps(execution.result, ensure_ascii=False)

    @tool("get_opportunity_by_id")
    def get_opportunity_by_id(id: str) -> str:
        """Retorna detalhes completos e a posição no portfólio de uma oportunidade, como OPP-MAR-01."""
        execution = registry.execute("get_opportunity_by_id", {"id": id})
        return json.dumps(execution.result, ensure_ascii=False)

    return [
        get_margin_opportunities,
        get_marketing_efficiency,
        get_inventory_opportunities,
        get_support_opportunities,
        get_prioritized_opportunities,
        get_opportunity_by_id,
    ]
