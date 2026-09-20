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
    "get_product_details",
    "get_product_ranking",
    "get_channel_margin",
    "get_break_even_point",
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
    (
        "get_break_even_point",
        (
            "break-even", "break even", "ponto de equilíbrio", "ponto de equilibrio",
            "aov mínimo", "aov minimo", "valor mínimo de carrinho", "valor minimo de carrinho",
            "ticket mínimo", "ticket minimo", "cesta mínima", "cesta minima",
            "frete não consuma a margem", "frete nao consuma a margem",
            "frete consumir a margem", "frete consome a margem", "frete não consuma margem",
        ),
    ),
    (
        "get_channel_margin",
        (
            "margem por canal", "margem de contribuição por canal", "margem de contribuicao por canal",
            "cm2", "cm 2", "cmii", "lucro por canal", "lucro líquido por canal",
            "lucro liquido por canal", "rentabilidade por canal", "contribuição por canal",
            "contribuicao por canal", "abertura de margem por canal",
        ),
    ),
    # Inventory comes before product queries so category/rupture/coverage questions stay in inventory.
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
        "get_product_ranking",
        (
            "ranking de produto", "ranking de produtos", "ranking por rentabilidade",
            "lista de produtos ordenados", "produtos ordenados", "mais rentáveis",
            "mais rentaveis", "maiores margens por produto", "maior margem por produto",
            "maior faturamento por produto", "mais vendidos por produto",
            "primeiro lugar na lista de produtos", "primeiro produto por rentabilidade",
            "primeiro lugar por rentabilidade", "qual produto", "qual é o produto",
            "produto com maior", "produto com menor", "top produtos", "top 5 produtos",
            "top 10 produtos", "ranking de skus", "ranking de sku",
        ),
    ),
    (
        "get_product_details",
        (
            "detalhes do produto", "dados do produto", "ficha do produto",
            "detalhes do sku", "dados do sku", "ficha do sku",
            "consultar sku", "informações do sku", "informacoes do sku",
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

    # A consulta explícita por SKU individual deve ser tratada como produto,
    # exceto quando houver um termo inequívoco de estoque/ruptura.
    if re.search(r"\bsku[- ]?\d{4,5}\b", q, re.IGNORECASE):
        inventory_terms = ("estoque", "ruptura", "cobertura", "reposição", "reposicao", "overstock")
        if not any(term in q for term in inventory_terms):
            return "get_product_details"

    # Ranking tem precedência sobre a palavra genérica "produto".
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
    q = question.lower()
    if re.search(r"(?:\b1\s*[ºo°]|\bprimeiro\b)", q):
        return 1
    match = re.search(r"\b(\d{1,2})\s+(?:skus?|itens?|produtos?)\b", q)
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

    if tool_name == "get_channel_margin":
        if "menor margem" in q or "menor rentabilidade" in q:
            return {"order_by": "margem_pct_apos_frete_antes_impostos", "descending": False}
        if "maior margem percentual" in q or "maior rentabilidade" in q:
            return {"order_by": "margem_pct_apos_frete_antes_impostos", "descending": True}
        if "maior receita" in q or "maior faturamento" in q:
            return {"order_by": "receita_liquida", "descending": True}
        return {"order_by": "margem_contribuicao_apos_frete_antes_impostos", "descending": True}

    if tool_name == "get_break_even_point":
        args: Dict[str, Any] = {}
        for category in ("beleza", "moda", "lifestyle", "acessórios", "acessorios"):
            if category in q:
                args["categoria"] = "Acessórios" if category in {"acessórios", "acessorios"} else category.title()
                break
        return args

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

    if tool_name == "get_product_ranking":
        order_by = "rentabilidade"
        if "faturamento" in q or "receita" in q:
            order_by = "faturamento"
        elif "margem" in q:
            order_by = "margem"
        elif "unidades" in q or "mais vendidos" in q or "maior volume" in q:
            order_by = "unidades"

        descending = not any(marker in q for marker in ("menor", "último", "ultimo", "piores", "bottom"))
        return {
            "order_by": order_by,
            "descending": descending,
            "limit": _extract_limit(q, default=10, maximum=50),
        }

    if tool_name == "get_product_details":
        sku_match = re.search(r"\bSKU[- ]?\d{4,5}\b", q, re.IGNORECASE)
        args: Dict[str, Any] = {"query": question}
        if sku_match:
            args["sku_id"] = sku_match.group(0).upper().replace(" ", "-")
        return args

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
