from __future__ import annotations

import re
from typing import Optional

TOOL_NAMES = (
    "get_margin_opportunities",
    "get_marketing_efficiency",
    "get_inventory_opportunities",
    "get_support_opportunities",
    "get_prioritized_opportunities",
)


def infer_tool_for_question(question: str) -> Optional[str]:
    """Deterministic guardrail for the five canonical executive intents.

    Returns a single authorized tool when the wording strongly identifies the
    business area. Returns None for ambiguous questions so the LLM can choose
    among the registered tools.
    """
    q = question.casefold()

    priority_terms = (
        "priorizar",
        "priorizadas",
        "priorizadas nos próximos",
        "30 dias",
        "60 dias",
        "90 dias",
        "quick win",
        "quick wins",
    )
    if any(term in q for term in priority_terms):
        return "get_prioritized_opportunities"

    margin_terms = (
        "margem",
        "prejuízo",
        "prejuizo",
        "perdendo dinheiro",
        "perdendo margem",
        "devoluç",
        "frete subsidiado",
    )
    if any(term in q for term in margin_terms):
        return "get_margin_opportunities"

    marketing_terms = (
        "marketing",
        "aquisição",
        "aquisicao",
        "canal",
        "canais",
        "roas",
        "cac",
        "verba",
        "mídia",
        "midia",
    )
    if any(term in q for term in marketing_terms):
        return "get_marketing_efficiency"

    inventory_terms = (
        "estoque",
        "stockout",
        "ruptura",
        "sku",
        "sks",
        "overstock",
        "excesso de estoque",
        "reposição",
        "reposicao",
    )
    if any(term in q for term in inventory_terms):
        return "get_inventory_opportunities"

    support_terms = (
        "atendimento",
        "ticket",
        "tickets",
        "wismo",
        "suporte",
        "csat",
        "chamados",
    )
    if any(term in q for term in support_terms):
        return "get_support_opportunities"

    return None
