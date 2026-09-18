from __future__ import annotations

import json
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

    def opportunities_by_area(self, area: str) -> List[Dict[str, Any]]:
        return [o for o in self.opportunities if o.get("area") == area]

    def opportunity_by_id(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        return next((o for o in self.opportunities if o.get("id") == opportunity_id), None)

    def prioritized(self) -> List[Dict[str, Any]]:
        return sorted(self.priority_portfolio, key=lambda x: x.get("rank", 10**9))

    def limited_view(self, items: Iterable[Dict[str, Any]], *, limit: int = 20) -> List[Dict[str, Any]]:
        return list(items)[:limit]
