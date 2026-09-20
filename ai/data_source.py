from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


REQUIRED_SALES_FILE = "vendas.csv"


def locate_data_room(context_path: str | Path, explicit: Optional[str | Path] = None) -> Optional[Path]:
    """Locate the Data Room without depending on the Dashboard artifacts."""
    context_path = Path(context_path).resolve()
    candidates = []

    if explicit:
        candidates.append(Path(explicit).expanduser())
    env_path = os.getenv("VERTICE_DATA_ROOM")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    base = context_path.parent
    candidates.extend(
        [
            base / "Data Room",
            base.parent / "Data Room",
            base.parent.parent / "Data Room",
            Path.cwd() / "Data Room",
            Path.cwd().parent / "Data Room",
        ]
    )

    seen = set()
    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if str(candidate) in seen:
            continue
        seen.add(str(candidate))
        if (candidate / REQUIRED_SALES_FILE).is_file():
            return candidate
    return None


def load_approved_sales(context_path: str | Path, data_room_path: Optional[str | Path] = None) -> Tuple[pd.DataFrame, Path]:
    """Load and minimally normalize vendas.csv using the validated case rules."""
    data_room = locate_data_room(context_path, data_room_path)
    if data_room is None:
        raise FileNotFoundError(
            "Data Room não localizado. Defina VERTICE_DATA_ROOM ou mantenha a pasta 'Data Room' "
            "em um diretório pai do Copilot. O Copilot não usa process_data.json como fonte factual."
        )

    vendas = pd.read_csv(data_room / REQUIRED_SALES_FILE, encoding="utf-8-sig", low_memory=False)
    vendas.columns = [str(col).strip() for col in vendas.columns]

    required = {"order_id", "canal", "status_pagamento", "receita_liquida", "custo_frete", "margem_contribuicao", "quantidade"}
    missing = required - set(vendas.columns)
    if missing:
        raise ValueError(f"vendas.csv não possui as colunas necessárias: {sorted(missing)}")

    # Tratamento validado do case: remover registros sem atributos financeiros essenciais.
    numeric_cols = [
        "quantidade",
        "preco_unitario",
        "receita_bruta",
        "desconto_reais",
        "receita_liquida",
        "custo_produto",
        "custo_frete",
        "margem_contribuicao",
    ]
    for col in numeric_cols:
        if col in vendas.columns:
            vendas[col] = pd.to_numeric(vendas[col], errors="coerce")

    if "data_pedido" in vendas.columns:
        vendas["data_pedido"] = pd.to_datetime(vendas["data_pedido"], errors="coerce")

    vendas = vendas.dropna(subset=["quantidade", "receita_liquida", "margem_contribuicao"]).copy()
    if "devolvido" in vendas.columns:
        vendas["devolvido_bool"] = vendas["devolvido"].astype(str).str.strip().str.lower().isin(["true", "1"])
    else:
        vendas["devolvido_bool"] = False
    vendas_aprovadas = vendas[vendas["status_pagamento"] == "Aprovado"].copy()
    return vendas_aprovadas, data_room


def detect_tax_columns(df: pd.DataFrame) -> list[str]:
    """Detect deterministic tax fields if the Data Room ever receives them."""
    normalized = {}
    for col in df.columns:
        key = (
            str(col)
            .strip()
            .lower()
            .replace("á", "a")
            .replace("à", "a")
            .replace("ã", "a")
            .replace("â", "a")
            .replace("é", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ô", "o")
            .replace("õ", "o")
            .replace("ú", "u")
        )
        normalized[col] = key

    candidates = {
        "imposto",
        "impostos",
        "valor_imposto",
        "imposto_reais",
        "tributo",
        "tributos",
        "valor_tributo",
        "taxa_imposto",
        "aliquota",
        "aliquota_imposto",
    }
    return [col for col, norm in normalized.items() if norm in candidates]
