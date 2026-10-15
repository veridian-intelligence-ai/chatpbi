"""
Contrato base para adapters de fontes de dados (Fabric, BigQuery, etc.).

Cada implementação concreta deve respeitar esta interface para que o
restante da plataforma possa tratar todas as fontes de forma uniforme.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SemanticModel:
    """Minimal placeholder — full schema chega na F.3."""

    id: str = ""
    name: str = ""
    workspace_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryResult:
    """Minimal placeholder — full schema chega na F.3."""

    columns: List[str] = field(default_factory=list)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseDataSourceAdapter(abc.ABC):
    """Interface comum a todos os adapters de fontes de dados."""

    @abc.abstractmethod
    def health_check(self) -> bool:
        """Confirma que o adapter consegue alcançar a sua fonte de dados."""

    @abc.abstractmethod
    def list_models(self) -> List[SemanticModel]:
        """Lista modelos semânticos disponíveis na fonte. (F.3)"""

    @abc.abstractmethod
    def execute_query(self, model_id: str, query: str) -> QueryResult:
        """Executa uma query sobre o modelo indicado. (F.3)"""
