"""Hierarquia de exceções específica do adapter Fabric / Power BI."""

from __future__ import annotations

from typing import Any, Dict, Optional


class FabricError(Exception):
    """Erro base do adapter Fabric."""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = context or {}


class FabricConfigError(FabricError):
    """Variáveis de ambiente em falta ou inválidas."""


class FabricAuthError(FabricError):
    """Falha no fluxo OAuth2 (credenciais inválidas, rede, etc.)."""


class FabricAPIError(FabricError):
    """Chamada à REST API devolveu status não-2xx."""
