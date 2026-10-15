"""
Modelo semântico "Cota parlamentar" (dados abertos da Câmara dos Deputados).

Tudo o que é específico deste modelo vive aqui e nos três ficheiros .md da
pasta: o contexto do modelo (SEMANTIC_MODEL.md e MODEL_SCHEMA.md), os exemplos
validados de DAX (dax_examples.md), as regras fundamentais do prompt, os
exemplos de voz, as sugestões iniciais e os rótulos dos visuais. O resto do
backend é genérico e lê estas constantes através de
`api.semantic_models.get_active_model()`.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DIRECTORY = Path(__file__).parent

# Nome do modelo semântico no Power BI e descrição curta do que contém.
MODEL_NAME = "Cota parlamentar"
MODEL_DESCRIPTION = (
    "gastos da cota parlamentar dos deputados federais, a partir dos dados "
    "abertos da Câmara dos Deputados"
)
DATA_SUBJECT = "os gastos da cota parlamentar"

# Fuso horário, língua por defeito das respostas e moeda dos valores.
TIMEZONE = "America/Sao_Paulo"
DEFAULT_LANGUAGE = "português do Brasil"
CURRENCY_LABEL = "reais (R$)"
# Código ISO 4217 da moeda, para o frontend formatar os valores (R$ 1.234,56).
CURRENCY_CODE = "BRL"

# Regras que vão no topo do bloco estático do prompt, antes do contexto do
# modelo (o equivalente às "REGRA FUNDAMENTAL" do modelo original).
FUNDAMENTAL_RULES = """# ⚠️ REGRA FUNDAMENTAL — Tempo: mês de competência, meses recentes incompletos

- O mês de uma despesa é o mês de competência (`Despesas[Data de competência]`,
  sempre no dia 1). Filtrar o tempo SEMPRE pela tabela `'Calendário'`.
- Os meses mais recentes ainda recebem notas: ao falar do ano corrente ou dos
  últimos meses, dizer que os números ainda estão incompletos.
- O ano corrente está incompleto: comparar com o ano anterior só nos mesmos
  meses (exemplo 7).
- A partir de agosto de 2025, a categoria Passagem aérea (SIGEPA) deixou de ter
  despesas nos arquivos da Câmara: avisar quando a pergunta envolver passagens
  ou comparar períodos antes e depois dessa data.

---

# ⚠️ REGRA FUNDAMENTAL #2 — Deputados e lideranças

As lideranças de partido também usam a cota (`Parlamentares[Tipo] = "Liderança"`,
UF "NA"). Em TODO ranking ou média de deputados, filtrar
`Parlamentares[Tipo] = "Deputado(a)"`, salvo pedido explícito para incluir as
lideranças. Para gasto por partido, usar `Despesas[Partido na época]`."""

# Exemplos de respostas em voz (só de estilo: os números vêm sempre da consulta).
VOICE_EXAMPLES = (
    "Em 2025, os deputados gastaram cerca de 240 milhões de reais com a cota, "
    "um pouco abaixo dos 250 milhões de 2024. Parte dessa diferença vem das "
    "passagens aéreas, que deixaram de aparecer nos arquivos a partir de agosto. "
    "Se quiser, posso abrir o gasto por categoria.\n\n"
    "A divulgação foi a maior categoria de 2025, com cerca de 102 milhões de "
    "reais, um pouco mais de 40 por cento de todo o gasto do ano. Posso mostrar "
    "quais empresas mais receberam nessa categoria."
)

# Sugestões iniciais do /suggestions. Placeholders resolvidos por
# build_context() a partir de CONTEXT_DAX.
SUGGESTION_TEMPLATES: List[str] = [
    # Volume
    "Quanto foi gasto com a cota em {ano_anterior}?",
    "Quantas despesas foram registradas em {ano_anterior}?",
    "Compare {ano_corrente} com o mesmo período de {ano_anterior}",
    "Como evoluiu o gasto mês a mês?",

    # Deputados
    "Quais os 10 deputados que mais gastaram em {ano_anterior}?",
    "Quanto {top_deputado} gastou em {ano_anterior}?",
    "Em que categorias {top_deputado} mais gastou?",

    # Categorias e fornecedores
    "Qual o gasto por categoria em {ano_anterior}?",
    "Quais empresas mais receberam por divulgação?",
    "Quanto foi gasto com passagens aéreas por ano?",
    "Qual o gasto médio por despesa em cada categoria?",

    # Partidos e estados
    "Quais partidos mais gastaram em {ano_anterior}?",
    "Qual o gasto médio por deputado em cada estado?",
    "Qual região do país mais gasta com a cota?",
    "Qual o gasto com combustíveis por estado?",

    # Outros
    "Quanto a Câmara glosou em {ano_anterior}?",
    "Quanto as lideranças de partido gastaram em {ano_anterior}?",
]


def _years(now: datetime) -> Dict[str, str]:
    return {"ano_corrente": str(now.year), "ano_anterior": str(now.year - 1)}


def build_context_dax(now: datetime) -> str:
    """Consulta leve que resolve {top_deputado}: quem mais gastou no ano anterior."""
    year = now.year - 1
    return f"""
EVALUATE
TOPN (
    1,
    SUMMARIZECOLUMNS (
        Parlamentares[Parlamentar],
        TREATAS ( {{ {year} }}, 'Calendário'[Ano] ),
        TREATAS ( {{ "Deputado(a)" }}, Parlamentares[Tipo] ),
        "Gasto", [Total gasto]
    ),
    [Gasto], DESC
)
""".strip()


def build_context(now: datetime, rows: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
    """Contexto para os placeholders. Sem linhas, {top_deputado} fica de fora."""
    context = _years(now)
    if rows:
        value = rows[0].get("Parlamentar")
        if isinstance(value, str) and value.strip():
            context["top_deputado"] = value.strip()
    return context


# Rótulos dos visuais para as colunas deste modelo (nome devolvido pela
# consulta → rótulo). Os nomes do modelo já são legíveis; só entram aqui os que
# o humanizador genérico estragaria (siglas) ou que pedem outro rótulo.
DIMENSION_LABELS: Dict[str, str] = {
    "UF": "UF",
    "UF atual": "UF",
    "Partido atual": "Partido",
    "Partido na época": "Partido",
    "CNPJ do fornecedor": "CNPJ",
    "Ano e mês": "Mês",
    "Gasto": "Gasto (R$)",
}

# Colunas que levam valores em dinheiro.
MONEY_LIKE_KEYS = {
    "Gasto",
    "Total gasto",
    "Gasto nos mesmos meses",
    "Média por deputado",
    "Total glosado",
    "Valor líquido",
    "Valor do documento",
    "Valor glosado",
    "Valor restituído",
}
