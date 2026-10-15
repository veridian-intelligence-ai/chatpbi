"""Contrato dos pacotes de modelo semântico (api/semantic_models/<modelo>/).

Os outros testes usam o modelo ativo (padrão: Cota parlamentar). Estes conferem
todos os pacotes de PACOTES, independentemente de SEMANTIC_MODEL: constantes do
prompt, sugestões, rótulos, arquivos de contexto e os exemplos de DAX.

Pacote novo entra em PACOTES, com uma linha de exemplo da consulta de contexto
(build_context_dax) no formato que build_context lê.
"""
from __future__ import annotations

import re
import string
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from api.semantic_models import get_model

PACOTES = {
    # pacote: linha de exemplo da consulta de contexto (nomes já normalizados)
    "cota_parlamentar": {"Parlamentar": "Fulano de Tal", "Gasto": 1000.0},
}
_AGORA = datetime(2026, 10, 15, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _placeholders(template: str) -> set[str]:
    return {nome for _, nome, _, _ in string.Formatter().parse(template) if nome}


def _blocos_dax(texto: str) -> list[str]:
    return [b.strip() for b in re.findall(r"```dax\n(.*?)```", texto, flags=re.S)]


@pytest.mark.parametrize("nome", sorted(PACOTES))
def test_pacote_tem_as_constantes(nome: str) -> None:
    m = get_model(nome)
    for attr in ("MODEL_NAME", "MODEL_DESCRIPTION", "DATA_SUBJECT", "DEFAULT_LANGUAGE",
                 "CURRENCY_LABEL", "FUNDAMENTAL_RULES", "VOICE_EXAMPLES"):
        assert isinstance(getattr(m, attr), str) and getattr(m, attr).strip(), attr
    ZoneInfo(m.TIMEZONE)
    assert re.fullmatch(r"[A-Z]{3}", m.CURRENCY_CODE)
    assert isinstance(m.DIMENSION_LABELS, dict)
    assert isinstance(m.MONEY_LIKE_KEYS, set) and m.MONEY_LIKE_KEYS
    assert Path(m.DIRECTORY).is_dir()


@pytest.mark.parametrize("nome", sorted(PACOTES))
def test_pacote_tem_os_arquivos_de_contexto(nome: str) -> None:
    pasta = Path(get_model(nome).DIRECTORY)
    for arquivo in ("SEMANTIC_MODEL.md", "MODEL_SCHEMA.md", "dax_examples.md"):
        assert (pasta / arquivo).read_text(encoding="utf-8").strip(), arquivo


@pytest.mark.parametrize("nome", sorted(PACOTES))
def test_exemplos_de_dax_sao_consultas(nome: str) -> None:
    blocos = _blocos_dax((Path(get_model(nome).DIRECTORY) / "dax_examples.md").read_text(encoding="utf-8"))
    assert len(blocos) >= 8
    for bloco in blocos:
        assert bloco.split()[0] in ("EVALUATE", "DEFINE"), bloco[:60]


@pytest.mark.parametrize("nome", sorted(PACOTES))
def test_sugestoes_resolvem_todos_os_placeholders(nome: str) -> None:
    m = get_model(nome)
    assert m.build_context_dax(_AGORA).lstrip().startswith("EVALUATE")
    contexto = {"current_month_pt": "Outubro de 2026", **m.build_context(_AGORA, [PACOTES[nome]])}
    assert len(m.SUGGESTION_TEMPLATES) >= 6
    for template in m.SUGGESTION_TEMPLATES:
        assert _placeholders(template) <= set(contexto), template
        assert "{" not in template.format(**contexto), template
    # Sem linhas (consulta falhou), o contexto não inventa o placeholder dinâmico.
    sem_linhas = m.build_context(_AGORA, None)
    assert set(sem_linhas) == {"ano_corrente", "ano_anterior"}
