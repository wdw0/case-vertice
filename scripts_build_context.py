from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
BASE_CONTEXT = ROOT / "data" / "vertice_ai_context.json"


def read_csv(data_room: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(data_room / name, encoding="utf-8-sig")


def build_views(data_room: Path) -> dict:
    marketing = read_csv(data_room, "marketing.csv")
    channels = (
        marketing.groupby("canal")
        .agg(
            investimento_total=("investimento_reais", "sum"),
            receita_gerada_total=("receita_gerada", "sum"),
            conversoes_total=("conversoes", "sum"),
            cliques_total=("cliques", "sum"),
            impressoes_total=("impressoes", "sum"),
            campanhas=("campanha_id", "count"),
        )
        .reset_index()
    )
    channels["roas"] = channels["receita_gerada_total"] / channels["investimento_total"]
    channels["cac"] = channels["investimento_total"] / channels["conversoes_total"]
    channels = channels.sort_values("roas", ascending=False)

    sales = read_csv(data_room, "vendas.csv")
    sales["data_pedido"] = pd.to_datetime(sales["data_pedido"], errors="coerce")
    for col in ["quantidade", "receita_liquida", "margem_contribuicao"]:
        sales[col] = pd.to_numeric(sales[col], errors="coerce")
    sales = sales.dropna(subset=["quantidade", "receita_liquida", "margem_contribuicao"])
    days = max((sales["data_pedido"].max() - sales["data_pedido"].min()).days, 1)

    inventory = read_csv(data_room, "estoque.csv")
    by_sku = (
        sales.groupby("sku_id")
        .agg(
            unidades_vendidas=("quantidade", "sum"),
            receita_historica=("receita_liquida", "sum"),
            margem_historica=("margem_contribuicao", "sum"),
            pedidos_count=("order_id", "nunique"),
        )
        .reset_index()
    )
    by_sku["demanda_media_diaria"] = by_sku["unidades_vendidas"] / days
    stock = inventory.merge(by_sku, on="sku_id", how="inner")
    stock["cobertura_teorica_dias"] = np.where(
        stock["demanda_media_diaria"] > 0,
        stock["estoque_disponivel"] / stock["demanda_media_diaria"],
        np.nan,
    )
    q75 = float(stock["unidades_vendidas"].quantile(0.75))
    stockout = stock[(stock["estoque_disponivel"] <= 0) & (stock["unidades_vendidas"] >= q75)].copy()
    stockout = stockout.sort_values("unidades_vendidas", ascending=False)
    high_coverage = stock[stock["cobertura_teorica_dias"] > 365].copy()
    high_coverage["capital_exposicao"] = high_coverage["estoque_disponivel"] * high_coverage["custo_unitario"]
    high_coverage = high_coverage.sort_values("capital_exposicao", ascending=False).head(15)

    support = read_csv(data_room, "atendimento.csv")
    support = support[support["ticket_id"].astype(str).str.upper() != "TKT"].copy()
    top_support = (
        support.groupby("customer_id")
        .agg(
            tickets=("ticket_id", "count"),
            custo=("custo_operacional_ticket", "sum"),
            csat=("nota_csat", "mean"),
        )
        .reset_index()
        .sort_values("tickets", ascending=False)
        .head(10)
    )
    top_support["share_pct"] = top_support["tickets"] / len(support) * 100

    def records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
        clean = df[cols].copy().replace({np.nan: None, np.inf: None, -np.inf: None})
        return json.loads(clean.to_json(orient="records", force_ascii=False))

    return {
        "marketing_channels": records(
            channels,
            ["canal", "investimento_total", "receita_gerada_total", "conversoes_total", "roas", "cac", "campanhas"],
        ),
        "inventory_stockouts_high_demand": records(
            stockout,
            ["sku_id", "nome_produto", "categoria", "estoque_disponivel", "unidades_vendidas", "receita_historica", "margem_historica", "lead_time_reposicao", "preco_venda_sugerido"],
        ),
        "inventory_high_coverage": records(
            high_coverage,
            ["sku_id", "nome_produto", "categoria", "estoque_disponivel", "unidades_vendidas", "cobertura_teorica_dias", "custo_unitario", "capital_exposicao"],
        ),
        "support_top_customers": records(
            top_support,
            ["customer_id", "tickets", "custo", "csat", "share_pct"],
        ),
        "method_notes": {
            "marketing_channels": "Agregado por canal; ROAS = receita_gerada_total / investimento_total; CAC = investimento_total / conversoes_total.",
            "inventory_stockouts_high_demand": f"SKU em ruptura e no quartil superior de unidades vendidas; histórico de vendas = {days} dias; q75 = {q75:.0f} unidades.",
            "inventory_high_coverage": "Cobertura teórica = estoque disponível / demanda média diária; exposição calculada como estoque disponível × custo unitário.",
            "support_top_customers": "Ordenação por quantidade de tickets válidos; concentração não implica churn individual.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Enriquece o contrato de contexto do Vértice Intelligence.")
    parser.add_argument("--data-room", required=True, help="Diretório contendo os CSVs do Data Room")
    parser.add_argument("--base-context", default=str(BASE_CONTEXT), help="Contexto v1.0 já exportado pela Etapa 1")
    parser.add_argument("--output", default=str(BASE_CONTEXT), help="Destino do contexto v1.1")
    args = parser.parse_args()

    data = json.loads(Path(args.base_context).read_text(encoding="utf-8"))
    data["schema_version"] = "1.1"
    data["analysis_views"] = build_views(Path(args.data_room))
    data["source"]["structured_views"] = "Derivadas deterministicamente dos CSVs do Data Room; não do process_data.json."
    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Contexto enriquecido: {args.output}")


if __name__ == "__main__":
    main()
