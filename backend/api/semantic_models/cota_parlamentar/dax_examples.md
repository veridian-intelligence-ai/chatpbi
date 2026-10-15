# Exemplos DAX Validados — Cota parlamentar

Os 11 exemplos abaixo rodaram no modelo semântico "Cota parlamentar" (DAX query view e notebook do Fabric) antes de entrar aqui. Os números citados nas respostas-modelo são os da validação e mudam a cada atualização dos dados: em produção, a resposta usa sempre o valor devolvido pela consulta. Servem como few-shot patterns para gerar DAX correto à primeira.

## Como escrever o DAX neste modelo

- A consulta sempre começa com EVALUATE (ou DEFINE, para variáveis, e depois EVALUATE) e devolve uma tabela pequena. Agrupe e resuma: nunca traga as linhas soltas de Despesas.
- Para agrupar, use SUMMARIZECOLUMNS. Ele já deixa de fora as linhas em que todas as medidas ficam vazias.
- Para filtrar, passe o filtro dentro do SUMMARIZECOLUMNS, com `TREATAS ({2025}, 'Calendário'[Ano])` ou `FILTER (ALL (coluna), condição)`.
- Para rankings, use TOPN e termine com ORDER BY.
- Dê às colunas calculadas nomes curtos e diferentes dos nomes das medidas, como "Gasto" em vez de "Total gasto".
- Sempre escreva o nome da tabela antes da coluna, como `'Calendário'[Ano]`. Calendário vai entre aspas simples por causa do acento.
- Quando um filtro de texto não achar nada, procure os valores que existem na coluna com VALUES antes de concluir que não há dado.

---

## Exemplo 1 — Valor único: total do período

**Pergunta:** "Quanto já foi gasto com a cota?"

```dax
EVALUATE
ROW (
    "Gasto", [Total gasto],
    "Despesas", [Quantidade de despesas],
    "Último mês", [Último mês com dados]
)
```

**Resposta-modelo (prosa, SEM visual_hint):**

> De janeiro de 2023 até outubro de 2026, a cota parlamentar somou **R$ 874,3 milhões** em 789.204 despesas.

**Notas:**
- Usar `ROW("Nome", valor)` com nome de coluna explícito para valor único (NÃO `{ (label, valor) }`, que devolve colunas anónimas Value1/Value2).
- Valor único → SEM `visual_hint`. O número vive na prosa, com destaque a negrito.

---

## Exemplo 2 — Série por ano

**Pergunta:** "Quanto foi gasto em cada ano?"

```dax
EVALUATE
SUMMARIZECOLUMNS ( 'Calendário'[Ano], "Gasto", [Total gasto] )
ORDER BY 'Calendário'[Ano]
```

**Resposta-modelo:** comparação compacta entre poucos anos (2023: R$ 245,5 milhões; 2024: R$ 250,4 milhões; 2025: R$ 240,4 milhões) → tabela markdown no texto, SEM `visual_hint`, avisando que o ano corrente está incompleto.

---

## Exemplo 3 — Top N de deputados num ano

**Pergunta:** "Quais os 10 deputados que mais gastaram em 2025?"

```dax
EVALUATE
TOPN (
    10,
    SUMMARIZECOLUMNS (
        Parlamentares[Parlamentar],
        Parlamentares[Partido atual],
        Parlamentares[UF atual],
        TREATAS ( { 2025 }, 'Calendário'[Ano] ),
        TREATAS ( { "Deputado(a)" }, Parlamentares[Tipo] ),
        "Gasto", [Total gasto]
    ),
    [Gasto], DESC
)
ORDER BY [Gasto] DESC
```

**visual_hint sugerido:**

```json
{
  "chart_type": "bar",
  "x_field": "Parlamentar",
  "y_field": "Gasto",
  "title": "Os 10 deputados que mais gastaram em 2025",
  "value_format": "currency"
}
```

**Notas:**
- Rankings de deputados filtram `Parlamentares[Tipo] = "Deputado(a)"` para deixar as lideranças de fora.
- Os nomes de coluna do `visual_hint` são os devolvidos pela consulta, sem o nome da tabela (`Parlamentar`, `Gasto`).

---

## Exemplo 4 — Eixo categórico com filtro de ano

**Pergunta:** "Qual o gasto por categoria em 2025?"

```dax
EVALUATE
SUMMARIZECOLUMNS (
    Categorias[Categoria],
    Categorias[Grupo],
    TREATAS ( { 2025 }, 'Calendário'[Ano] ),
    "Gasto", [Total gasto]
)
ORDER BY [Gasto] DESC
```

**visual_hint sugerido:**

```json
{
  "chart_type": "bar",
  "x_field": "Categoria",
  "y_field": "Gasto",
  "title": "Gasto por categoria em 2025",
  "value_format": "currency"
}
```

**Notas:**
- Na validação, Divulgação foi a maior categoria de 2025, com R$ 102,1 milhões.

---

## Exemplo 5 — Evolução mensal com visual_hint

**Pergunta:** "Como evoluiu o gasto mês a mês?"

```dax
EVALUATE
SUMMARIZECOLUMNS ( 'Calendário'[Ano e mês], "Gasto", [Total gasto] )
ORDER BY 'Calendário'[Ano e mês]
```

**visual_hint sugerido:**

```json
{
  "chart_type": "line",
  "x_field": "Ano e mês",
  "y_field": "Gasto",
  "title": "Gasto mês a mês",
  "value_format": "currency"
}
```

**Notas:**
- `'Calendário'[Ano e mês]` é texto AAAA-MM: já sai em ordem cronológica.
- Avisar que os últimos meses ainda recebem notas e vão crescer.

---

## Exemplo 6 — Achar um parlamentar pelo nome

**Pergunta:** "Quanto a Tabata gastou?"

```dax
EVALUATE
SUMMARIZECOLUMNS (
    Parlamentares[Parlamentar],
    Parlamentares[Partido atual],
    Parlamentares[UF atual],
    FILTER (
        ALL ( Parlamentares[Parlamentar] ),
        CONTAINSSTRING ( Parlamentares[Parlamentar], "tabata" )
    ),
    "Gasto", [Total gasto]
)
```

**Notas:**
- CONTAINSSTRING não diferencia maiúsculas de minúsculas.
- Se vier mais de uma linha, confirmar com o utilizador qual é a pessoa antes de responder.

---

## Exemplo 7 — Ano corrente contra o anterior, nos mesmos meses

**Pergunta:** "O gasto deste ano está acima ou abaixo do ano passado?"

```dax
DEFINE
    VAR UltimaData = CALCULATE ( MAX ( Despesas[Data de competência] ), REMOVEFILTERS () )
    VAR UltimoMes = MONTH ( UltimaData )
EVALUATE
SUMMARIZECOLUMNS (
    'Calendário'[Ano],
    FILTER ( ALL ( 'Calendário'[Número do mês] ), 'Calendário'[Número do mês] <= UltimoMes ),
    "Gasto nos mesmos meses", [Total gasto]
)
ORDER BY 'Calendário'[Ano]
```

**Notas:**
- Compara de janeiro até o último mês com dados em todos os anos, para não comparar um ano incompleto com um ano inteiro.
- Comparação compacta → tabela markdown no texto, SEM `visual_hint`, com a diferença em % e em reais.

---

## Exemplo 8 — Gasto por partido na época da despesa

**Pergunta:** "Quais partidos mais gastaram em 2025?"

```dax
EVALUATE
SUMMARIZECOLUMNS (
    Despesas[Partido na época],
    TREATAS ( { 2025 }, 'Calendário'[Ano] ),
    "Gasto", [Total gasto],
    "Deputados", [Parlamentares com gasto]
)
ORDER BY [Gasto] DESC
```

**visual_hint sugerido:**

```json
{
  "chart_type": "bar",
  "x_field": "Partido na época",
  "y_field": "Gasto",
  "title": "Gasto por partido em 2025",
  "value_format": "currency"
}
```

---

## Exemplo 9 — Média por deputado em cada estado

**Pergunta:** "Qual o gasto médio por deputado em cada estado em 2025?"

```dax
EVALUATE
SUMMARIZECOLUMNS (
    Estados[UF],
    Estados[Estado],
    TREATAS ( { 2025 }, 'Calendário'[Ano] ),
    TREATAS ( { "Deputado(a)" }, Parlamentares[Tipo] ),
    "Gasto", [Total gasto],
    "Deputados", [Parlamentares com gasto],
    "Média por deputado", DIVIDE ( [Total gasto], [Parlamentares com gasto] )
)
ORDER BY [Média por deputado] DESC
```

**visual_hint sugerido:**

```json
{
  "chart_type": "bar",
  "x_field": "UF",
  "y_field": "Média por deputado",
  "title": "Gasto médio por deputado em 2025, por estado",
  "value_format": "currency"
}
```

---

## Exemplo 10 — Empresas que mais receberam, agrupadas pelo CNPJ

**Pergunta:** "Quais as 10 empresas que mais receberam em divulgação?"

```dax
EVALUATE
TOPN (
    10,
    SUMMARIZECOLUMNS (
        Despesas[CNPJ do fornecedor],
        TREATAS ( { "Divulgação" }, Categorias[Categoria] ),
        TREATAS ( { "Empresa" }, Despesas[Tipo de fornecedor] ),
        "Fornecedor", MAX ( Despesas[Fornecedor] ),
        "Gasto", [Total gasto]
    ),
    [Gasto], DESC
)
ORDER BY [Gasto] DESC
```

**visual_hint sugerido:**

```json
{
  "chart_type": "bar",
  "x_field": "Fornecedor",
  "y_field": "Gasto",
  "title": "As 10 empresas que mais receberam em divulgação",
  "value_format": "currency"
}
```

**Notas:**
- A mesma empresa aparece com nomes escritos de jeitos diferentes: agrupar pelo CNPJ e mostrar um dos nomes com `MAX(Despesas[Fornecedor])`.

---

## Exemplo 11 — Passagens aéreas por ano, somando as três categorias

**Pergunta:** "Quanto foi gasto com passagens aéreas por ano?"

```dax
EVALUATE
SUMMARIZECOLUMNS (
    'Calendário'[Ano],
    FILTER (
        ALL ( Categorias[Categoria] ),
        LEFT ( Categorias[Categoria], 14 ) = "Passagem aérea"
    ),
    "Gasto", [Total gasto]
)
ORDER BY 'Calendário'[Ano]
```

**Notas:**
- Soma Passagem aérea (SIGEPA), (RPA) e (reembolso).
- Avisar que a SIGEPA deixou de ter despesas nos arquivos a partir de agosto de 2025, o que distorce a comparação entre anos.

---

## Padrões a evitar (anti-padrões)

❌ **NUNCA** recalcular o gasto com `SUM(Despesas[Valor do documento])`: o gasto é o valor líquido, pela medida `[Total gasto]`.

❌ **NUNCA** filtrar o tempo pelas colunas ocultas `Despesas[Ano]` ou `Despesas[Mês]`: filtrar sempre pela tabela `'Calendário'`.

❌ **NUNCA** comparar o ano corrente inteiro com o ano anterior inteiro: o ano corrente está incompleto (usar o exemplo 7).

❌ **NUNCA** montar ranking de deputados sem `Parlamentares[Tipo] = "Deputado(a)"`: as lideranças entram no topo e não são pessoas.

❌ **NUNCA** usar um table constructor `{ ... }` como expressão do EVALUATE: devolve colunas anónimas (Value1, Value2). Usar `ROW("Nome", expr)`.
