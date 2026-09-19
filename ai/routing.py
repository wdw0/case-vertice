from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

AUTHORIZED_TOOLS = (
    "get_margin_opportunities",
    "get_marketing_efficiency",
    "get_inventory_opportunities",
    "get_support_opportunities",
    "get_prioritized_opportunities",
    "get_opportunity_by_id",
)

ROUTES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "get_opportunity_by_id",
        ("opp-mar-", "opp-mkt-", "opp-est-", "opp-atd-"),
    ),
    (
        "get_prioritized_opportunities",
        (
            "prioriz", "prioridade", "prioridades", "priorizar",
            "30 dias", "60 dias", "90 dias", "quick win", "quick wins",
            "portfólio priorizado", "portfolio priorizado", "todas as frentes",
            "todas as áreas", "toda a empresa", "panorama geral", "visão geral",
            "visao geral", "problemas em geral", "outras frentes",
        ),
    ),
    # Inventory comes before margin so stock queries are kept in the inventory domain.
    (
        "get_inventory_opportunities",
        (
            "estoque", "ruptura", "rupturas", "sku", "skus",
            "excesso de estoque", "cobertura", "inventário", "reposição", "reposicao",
            "overstock", "itens da categoria", "categoria beleza", "categoria moda",
            "categoria lifestyle", "categoria acessórios", "categoria acessorios",
            "itens de beleza", "item de beleza", "produtos de beleza",
            "itens de moda", "item de moda", "produtos de moda",
            "itens de lifestyle", "produtos de lifestyle",
            "itens de acessórios", "itens de acessorios", "produtos de acessórios", "produtos de acessorios",
            "perda de estoque", "prejuízo de estoque", "prejuizo de estoque",
        ),
    ),
    (
        "get_margin_opportunities",
        (
            "margem", "prejuízo", "prejuizo", "lucratividade", "rentabilidade",
            "devolução", "devoluções", "retorno", "frete negativo", "frete", "subsídio",
        ),
    ),
    (
        "get_marketing_efficiency",
        (
            "marketing", "canal", "canais", "roas", "cac", "aquisição",
            "aquisição de clientes", "investimento em mídia", "verba", "campanha", "campanhas",
        ),
    ),
    (
        "get_support_opportunities",
        (
            "atendimento", "suporte", "ticket", "tickets", "wismo", "sac",
            "cliente com muitos chamados", "chamados",
        ),
    ),
)


def infer_tool_for_question(question: str) -> Optional[str]:
    q = " ".join(question.lower().strip().split())
    for tool_name, keywords in ROUTES:
        if any(keyword in q for keyword in keywords):
            return tool_name
    return None


def infer_tool_for_followup(
    question: str,
    conversation: Iterable[Dict[str, object]],
) -> Optional[str]:
    q = question.lower().strip()
    followup_markers = (
        "isso", "isso aí", "isso mesmo", "esse", "essa", "esses", "essas",
        "detalhe", "detalhar", "detalhes", "aprofund", "plano", "ação que comentou",
        "comentou", "anterior", "acima", "melhor", "segunda", "primeira", "terceira",
        "qual desses", "qual dessas", "qual dos dois", "qual das duas",
        "e nesse caso", "e nesse cenário", "e sobre isso", "e nesse plano",
    )
    if not any(marker in q for marker in followup_markers):
        return None

    allowed = set(AUTHORIZED_TOOLS)
    turns = list(conversation)
    for turn in reversed(turns[-6:]):
        for tool in reversed(list(turn.get("tools_used") or [])):
            if tool in allowed:
                return tool
        for audit in reversed(list(turn.get("audit") or [])):
            if audit.get("status") == "final":
                payload = audit.get("payload") or {}
                for tool in reversed(list(payload.get("tools_used") or [])):
                    if tool in allowed:
                        return tool
    return None


def _extract_limit(question: str, default: int = 10, maximum: int = 50) -> int:
    match = re.search(r"\b(\d{1,2})\s+(?:skus?|itens?|produtos?)\b", question.lower())
    if not match:
        return default
    return max(1, min(maximum, int(match.group(1))))


def infer_tool_arguments(question: str, tool_name: Optional[str]) -> Dict[str, Any]:
    """Converte sinais explícitos da pergunta em argumentos determinísticos."""
    if not tool_name:
        return {}

    q = " ".join(question.lower().strip().split())

    if tool_name == "get_opportunity_by_id":
        match = re.search(r"opp-(?:mar|mkt|est|atd)-\d+", q, re.IGNORECASE)
        return {"id": match.group(0).upper()} if match else {}

    if tool_name == "get_marketing_efficiency":
        if "menor cac" in q or "menor custo de aquisição" in q or "cac mais baixo" in q:
            return {"order_by": "cac", "descending": False}
        if "maior cac" in q or "pior cac" in q:
            return {"order_by": "cac", "descending": True}
        if "maior investimento" in q:
            return {"order_by": "investimento", "descending": True}
        if "menor investimento" in q:
            return {"order_by": "investimento", "descending": False}
        if "maior receita" in q or "maior retorno" in q:
            return {"order_by": "receita", "descending": True}
        return {"order_by": "roas", "descending": True}

    if tool_name == "get_inventory_opportunities":
        args: Dict[str, Any] = {"limit": _extract_limit(q)}
        sku_match = re.search(r"\bSKU[- ]?\d{4,5}\b", q, re.IGNORECASE)
        if sku_match:
            args["sku_id"] = sku_match.group(0).upper().replace(" ", "-")
        for category in ("beleza", "moda", "lifestyle", "acessórios", "acessorios"):
            if category in q:
                args["categoria"] = "Acessórios" if category in {"acessórios", "acessorios"} else category.title()
                break
        if "prejuízo" in q or "prejuizo" in q or "perda" in q or "impacto financeiro" in q:
            # A base não observa prejuízo realizado por SKU em ruptura.
            # Ordenamos pela receita potencial bloqueada estimada durante o lead time.
            args["stockout_order_by"] = "receita_potencial_bloqueada_estimada"
            args["coverage_order_by"] = "capital_exposicao"
        elif "maior margem" in q or "margem histórica" in q or "margem historica" in q:
            args["stockout_order_by"] = "margem_historica"
        elif "mais vendidos" in q or "maior demanda" in q or "maior giro" in q:
            args["stockout_order_by"] = "unidades_vendidas"
        elif "maior lead time" in q or "maior prazo" in q:
            args["stockout_order_by"] = "lead_time_reposicao"
        else:
            args["stockout_order_by"] = "unidades_vendidas"
        return args

    if tool_name == "get_support_opportunities":
        return {"limit": _extract_limit(q, default=10, maximum=20)}

    return {}
