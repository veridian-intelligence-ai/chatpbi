"""
Modelos semânticos que o backend sabe consultar.

Cada modelo é um pacote nesta pasta (ex.: `cota_parlamentar`) com o contexto
do modelo em Markdown (SEMANTIC_MODEL.md, MODEL_SCHEMA.md, dax_examples.md) e
as constantes do prompt, das sugestões e dos visuais no `__init__.py`.

O modelo activo vem da variável de ambiente SEMANTIC_MODEL (nome do pacote).
Trocar a fonte de dados = criar um pacote novo, apontar
FABRIC_DEFAULT_DATASET_ID para o modelo no Power BI e mudar SEMANTIC_MODEL.
"""
from __future__ import annotations

import importlib
import os
from functools import lru_cache
from types import ModuleType

DEFAULT_SEMANTIC_MODEL = "cota_parlamentar"


@lru_cache(maxsize=None)
def get_model(name: str) -> ModuleType:
    """Importa o pacote do modelo `name` (fail-fast se não existir)."""
    if not name.isidentifier():
        raise RuntimeError(f"SEMANTIC_MODEL inválido: {name!r}")
    try:
        return importlib.import_module(f"api.semantic_models.{name}")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"SEMANTIC_MODEL={name!r} não existe em api/semantic_models/"
        ) from exc


def get_active_model() -> ModuleType:
    """Pacote do modelo activo, escolhido por SEMANTIC_MODEL."""
    name = os.getenv("SEMANTIC_MODEL", DEFAULT_SEMANTIC_MODEL).strip() or DEFAULT_SEMANTIC_MODEL
    return get_model(name)
