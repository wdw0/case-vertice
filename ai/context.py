from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class ContextStore:
    """Read-only access to the audited Vértice AI context contract."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Contexto não encontrado: {self.path}")
        with self.path.open("r", encoding="utf-8") as f:
            self.data: Dict[str, Any] = json.load(f)
        self._validate_contract()

    def _validate_contract(self) -> None:
        required = {
            "schema_version",
            "executive_kpis",
            "opportunities",
            "priority_portfolio",
            "governance",
        }
        missing = required - self.data.keys()
        if missing:
            raise ValueError(f"Contexto inválido; campos ausentes: {sorted(missing)}")

        product_view = (self.data.get("analysis_views") or {}).get("product_analytics")
        if product_view is not None and not isinstance(product_view.get("records"), list):
            raise ValueError("Contexto inválido; product_analytics.records deve ser uma lista")

    @property
    def kpis(self) -> Dict[str, Any]:
        return self.data["executive_kpis"]

    @property
    def opportunities(self) -> List[Dict[str, Any]]:
        return self.data["opportunities"]

    @property
    def priority_portfolio(self) -> List[Dict[str, Any]]:
        return self.data["priority_portfolio"]

    @property
    def governance(self) -> Dict[str, Any]:
        return self.data["governance"]

    @property
    def product_analytics(self) -> Dict[str, Any]:
        return (self.data.get("analysis_views") or {}).get("product_analytics") or {}

    @property
    def products(self) -> List[Dict[str, Any]]:
        return list(self.product_analytics.get("records") or [])

    @property
    def product_names(self) -> List[str]:
        return [str(p.get("produto", "")) for p in self.products if p.get("produto")]

    @property
    def product_skus(self) -> List[str]:
        return [str(p.get("sku_id", "")) for p in self.products if p.get("sku_id")]

    def opportunities_by_area(self, area: str) -> List[Dict[str, Any]]:
        return [o for o in self.opportunities if o.get("area") == area]

    def opportunity_by_id(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        return next((o for o in self.opportunities if o.get("id") == opportunity_id), None)

    def prioritized(self) -> List[Dict[str, Any]]:
        return sorted(self.priority_portfolio, key=lambda x: x.get("rank", 10**9))

    def limited_view(self, items: Iterable[Dict[str, Any]], *, limit: int = 20) -> List[Dict[str, Any]]:
        return list(items)[:limit]

    @staticmethod
    def normalize_product_text(value: str) -> str:
        value = unicodedata.normalize("NFKD", str(value or ""))
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = re.sub(r"[^a-zA-Z0-9]+", " ", value.lower())
        return " ".join(value.split())

    def find_products(self, query: str, *, limit: int = 5) -> List[Dict[str, Any]]:
        """Busca determinística por SKU exato ou nome de produto contido na pergunta."""
        q = str(query or "").strip()
        if not q:
            return []
        normalized_q = self.normalize_product_text(q)

        sku_match = re.search(r"\bsku[- ]?(\d{4,5})\b", q, re.IGNORECASE)
        if sku_match:
            target_sku = f"SKU-{int(sku_match.group(1)):05d}"
            exact = [p for p in self.products if str(p.get("sku_id", "")).upper() == target_sku]
            if exact:
                return exact[:limit]

        matches: List[tuple[int, Dict[str, Any]]] = []
        for product in self.products:
            name = str(product.get("produto") or "")
            normalized_name = self.normalize_product_text(name)
            if normalized_name and normalized_name in normalized_q:
                matches.append((len(normalized_name), product))

        matches.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in matches[:limit]]

    def product_by_sku(self, sku_id: str) -> Optional[Dict[str, Any]]:
        target = str(sku_id or "").upper().replace(" ", "-")
        if target and not target.startswith("SKU-") and target.isdigit():
            target = f"SKU-{int(target):05d}"
        return next((p for p in self.products if str(p.get("sku_id", "")).upper() == target), None)
