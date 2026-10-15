# Modelo semântico `Cota parlamentar` — dados abertos da Câmara dos Deputados

## O que são os dados

A Cota para o Exercício da Atividade Parlamentar (CEAP), a cota parlamentar, é o valor que cada deputado federal pode usar por mês para pagar despesas do mandato, como passagens, combustível, divulgação e escritório. Cada despesa aparece nos dados com o valor do documento e o valor que a Câmara reembolsou.

Os dados são públicos, dos dados abertos da Câmara dos Deputados (https://dadosabertos.camara.leg.br). Vão de janeiro de 2023, começo da legislatura atual, até o último mês carregado. A medida [Último mês com dados] diz qual é. Os valores estão em reais (R$).

O modelo semântico se chama "Cota parlamentar" e fica no Power BI, em Direct Lake, em cima das tabelas do lakehouse.

## Medidas (9)

Todas ficam na tabela Despesas.

| Medida | O que é |
|---|---|
| [Total gasto] | Soma do valor líquido reembolsado (Despesas[Valor líquido]). É o gasto. |
| [Quantidade de despesas] | Número de documentos de despesa. |
| [Gasto médio por despesa] | Total gasto dividido pela quantidade de despesas. |
| [Total glosado] | Valor que a Câmara não reembolsou. |
| [Parlamentares com gasto] | Número de parlamentares com pelo menos uma despesa. |
| [Total gasto no ano anterior] | Total gasto no mesmo período do ano anterior, pelo Calendário. |
| [Variação sobre o ano anterior] | Crescimento sobre o mesmo período do ano anterior, em percentual. |
| [Total gasto no acumulado do ano] | Total de janeiro até o mês do contexto. |
| [Último mês com dados] | Mês mais recente com despesas carregadas. |

Atenção com [Total gasto no ano anterior] e [Variação sobre o ano anterior] no ano corrente: com o filtro no ano inteiro, elas comparam o ano incompleto com o ano anterior completo. No ano corrente, use o exemplo 7.

---

## Glossário — termos → modelo

| Termo | Modelo | Notas |
|---|---|---|
| Gasto, despesa, quanto gastou | medida `[Total gasto]` | Valor líquido reembolsado pela Câmara |
| Número de despesas, notas, recibos | medida `[Quantidade de despesas]` | Um documento por linha |
| Glosa, valor não reembolsado | medida `[Total glosado]` | Parte do documento que a Câmara recusou |
| Deputado, parlamentar | `Parlamentares[Parlamentar]` | Nome parlamentar publicado pela Câmara |
| Liderança de partido | `Parlamentares[Tipo] = "Liderança"` | Também usa a cota; sem estado (UF "NA") |
| Partido | `Despesas[Partido na época]` | Partido quando a despesa foi feita |
| Partido atual | `Parlamentares[Partido atual]` | Partido na despesa mais recente |
| Estado, UF | `Estados[UF]`, `Estados[Estado]` | Estado do parlamentar quando a despesa foi feita |
| Região | `Estados[Região]` | Norte, Nordeste, Centro-Oeste, Sudeste, Sul |
| Categoria, tipo de gasto | `Categorias[Categoria]` | 21 categorias com nome simplificado |
| Grupo de gasto | `Categorias[Grupo]` | Transporte, Divulgação, Escritório, Serviços, Hospedagem e alimentação, Moradia |
| Passagens aéreas | categorias que começam com "Passagem aérea" | Somar SIGEPA, RPA e reembolso (exemplo 11) |
| Fornecedor, empresa | `Despesas[Fornecedor]`, `Despesas[CNPJ do fornecedor]` | Agrupar pelo CNPJ (exemplo 10) |
| Pessoa física | `Despesas[Tipo de fornecedor] = "Pessoa física"` | Sem nome nem CPF |
| Mês da despesa | `Despesas[Data de competência]` → `'Calendário'[Data]` | Mês de competência, sempre no dia 1 |
| Ano, mês, trimestre | `'Calendário'[Ano]`, `'Calendário'[Mês]`, `'Calendário'[Ano e mês]`, `'Calendário'[Trimestre]` | Filtrar o tempo sempre pelo Calendário |

---

## Regras de negócio obrigatórias

- Gasto é o valor líquido reembolsado pela Câmara. Use sempre as medidas do modelo, sem recalcular por conta própria.
- Alguns lançamentos são negativos, como a compensação de uma passagem aérea. Não filtre valores negativos: as medidas já fazem a conta certa.
- O mês de uma despesa é o mês de competência. A coluna Despesas[Data de competência] guarda sempre o dia 1 do mês. Para filtrar o tempo, use a tabela Calendário.
- Os meses mais recentes ainda recebem notas, e os valores deles crescem nas próximas atualizações. Ao falar do ano corrente ou dos últimos meses, avise que os números ainda estão incompletos.
- O ano corrente está incompleto. Para comparar com o ano anterior, compare os mesmos meses dos dois anos (exemplo 7).
- A partir de agosto de 2025, a categoria Passagem aérea (SIGEPA) deixou de ter despesas nos arquivos publicados pela Câmara. Por isso, comparações de passagens aéreas, ou do total gasto, entre períodos antes e depois de agosto de 2025 ficam distorcidas. Avise isso quando a pergunta envolver passagens ou comparar esses períodos.
- As lideranças de partido, como a Liderança do PT, também usam a cota. Elas aparecem em Parlamentares com Tipo igual a "Liderança" e sem estado (UF igual a "NA"). Em rankings de deputados, filtre Tipo igual a "Deputado(a)".
- Partido: Despesas[Partido na época] é o partido do deputado quando a despesa foi feita, e Parlamentares[Partido atual] é o partido na despesa mais recente. Para gasto por partido, use o partido na época.
- Fornecedor pessoa física aparece só como "Pessoa física", sem nome nem CPF. Não tente identificar a pessoa.
- A mesma empresa pode aparecer com o nome escrito de jeitos diferentes. Para somar por empresa, agrupe pelo CNPJ e mostre um dos nomes (exemplo 10).
- Os nomes de parlamentares são os nomes parlamentares publicados pela Câmara, com iniciais maiúsculas. Para achar alguém pelo nome, procure com CONTAINSSTRING, que não diferencia maiúsculas de minúsculas (exemplo 6). Se aparecer mais de um nome, confirme qual é antes de responder.

---

## Perguntas-tipo suportadas

**1. Quanto foi gasto com a cota em um ano?**
- Medida: `[Total gasto]`
- Filtro: `TREATAS({ano}, 'Calendário'[Ano])` (exemplos 1 e 2)

**2. Quais deputados mais gastaram?**
- Medida: `[Total gasto]`
- Eixo: `Parlamentares[Parlamentar]`, com partido e UF atuais
- Filtro: `Parlamentares[Tipo] = "Deputado(a)"` e o ano (exemplo 3)

**3. Em que categorias foi o gasto?**
- Medida: `[Total gasto]`
- Eixo: `Categorias[Categoria]`, `Categorias[Grupo]` (exemplo 4)

**4. Como evoluiu o gasto mês a mês?**
- Medida: `[Total gasto]`
- Eixo: `'Calendário'[Ano e mês]` (exemplo 5)

**5. Quanto um deputado gastou?**
- Filtro por nome com CONTAINSSTRING (exemplo 6)

**6. O ano corrente está acima ou abaixo do anterior?**
- Comparar os mesmos meses dos dois anos (exemplo 7)

**7. Quais partidos mais gastaram?**
- Eixo: `Despesas[Partido na época]` (exemplo 8)

**8. Qual o gasto médio por deputado em cada estado?**
- `DIVIDE([Total gasto], [Parlamentares com gasto])` por `Estados[UF]` (exemplo 9)

**9. Quais empresas mais receberam?**
- Agrupar por `Despesas[CNPJ do fornecedor]` e mostrar `MAX(Despesas[Fornecedor])` (exemplo 10)

**10. Quanto foi gasto com passagens aéreas?**
- Somar as três categorias de passagem aérea (exemplo 11) e avisar da mudança de agosto de 2025

**11. Quanto a Câmara glosou?**
- Medida: `[Total glosado]`, com o mesmo padrão de filtros das outras medidas

**12. Qual região do país gasta mais?**
- Eixo: `Estados[Região]`, filtrando `Parlamentares[Tipo] = "Deputado(a)"`
