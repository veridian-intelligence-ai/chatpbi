# MODEL_SCHEMA — `Cota parlamentar`

Esquema do modelo semântico "Cota parlamentar" do Power BI (Direct Lake, sobre as tabelas do lakehouse `cota_parlamentar`). As colunas marcadas como ocultas não aparecem para quem monta relatórios, mas podem ser usadas no DAX. As regras de negócio ficam em SEMANTIC_MODEL.md.

---

## Tables

### `Despesas`

Uma linha por documento de despesa: a nota fiscal, o recibo ou o bilhete. É a tabela de fatos. Guarda também as medidas do modelo.

| Coluna | O que é |
|---|---|
| `Data de competência` | Mês a que a despesa se refere, sempre no dia 1. Liga ao Calendário. |
| `Data de emissão` | Data de emissão da nota ou do recibo. Pode estar vazia. |
| `Partido na época` | Sigla do partido do parlamentar quando a despesa foi feita. Vazia nas lideranças. |
| `Especificação` | Detalhe da categoria, quando a Câmara informa (por exemplo, o tipo de combustível). |
| `Fornecedor` | Nome da empresa que recebeu. Pessoa física aparece só como "Pessoa física". |
| `CNPJ do fornecedor` | CNPJ da empresa, só com números. Vazio para pessoa física. |
| `Tipo de fornecedor` | "Empresa", "Pessoa física" ou "Não informado". |
| `Trecho` | Trecho da viagem, nas passagens. |
| `Valor do documento` | Valor da nota ou do recibo, em reais. |
| `Valor glosado` | Parte do valor que a Câmara não reembolsou. |
| `Valor líquido` | Valor reembolsado: o valor do documento menos a glosa. É o gasto. |
| `Valor restituído` | Valor devolvido pelo parlamentar. |
| `Documento` (oculta) | Identificador do documento na Câmara. |
| `Ano`, `Mês` (ocultas) | Ano e mês de competência. Prefira filtrar pelo Calendário. |
| `parlamentar_id`, `categoria_id`, `uf` (ocultas) | Chaves das relações. |

### `Parlamentares`

Um parlamentar ou liderança por linha.

| Coluna | O que é |
|---|---|
| `Parlamentar` | Nome parlamentar. |
| `Tipo` | "Deputado(a)" ou "Liderança". |
| `Partido atual` | Partido na despesa mais recente. |
| `UF atual` | Estado na despesa mais recente. "NA" nas lideranças. |
| `parlamentar_id` (oculta) | Chave. |

### `Categorias`

Os tipos de gasto da cota.

| Coluna | O que é |
|---|---|
| `Categoria` | Tipo de gasto, com nome simplificado. |
| `Grupo` | Grupo da categoria. |
| `Descrição oficial` | Nome da categoria como a Câmara publica. |
| `categoria_id` (oculta) | Chave. |

Categorias e grupos:

| Categoria | Grupo |
|---|---|
| Divulgação | Divulgação |
| Locação de veículos | Transporte |
| Escritório de apoio | Escritório |
| Passagem aérea (SIGEPA) | Transporte |
| Passagem aérea (RPA) | Transporte |
| Passagem aérea (reembolso) | Transporte |
| Combustíveis | Transporte |
| Táxi, pedágio e estacionamento | Transporte |
| Passagens terrestres, marítimas ou fluviais | Transporte |
| Fretamento de aeronaves | Transporte |
| Fretamento de embarcações | Transporte |
| Telefonia | Escritório |
| Serviços postais | Escritório |
| Assinatura de publicações | Escritório |
| Tokens e certificados digitais | Escritório |
| Consultorias e pesquisas | Serviços |
| Segurança | Serviços |
| Cursos e eventos | Serviços |
| Alimentação | Hospedagem e alimentação |
| Hospedagem | Hospedagem e alimentação |
| Complementação do auxílio-moradia | Moradia |

As passagens aéreas aparecem em três categorias, como a Câmara publica: SIGEPA, RPA e reembolso. Para "passagens aéreas", some as três: filtre as categorias que começam com "Passagem aérea" (exemplo 11).

### `Estados`

Os 27 estados e uma linha para as lideranças, que não têm estado.

| Coluna | O que é |
|---|---|
| `UF` | Sigla do estado. "NA" para as lideranças. |
| `Estado` | Nome do estado. "Sem estado (lideranças)" para NA. |
| `Região` | Norte, Nordeste, Centro-Oeste, Sudeste, Sul ou "Sem região". |

### `Calendário`

Um dia por linha, de 2023 a 2026. É a tabela de datas do modelo. Vai entre aspas simples no DAX por causa do acento: `'Calendário'[Ano]`.

| Coluna | O que é |
|---|---|
| `Data` | Data. Liga a Despesas[Data de competência]. |
| `Ano` | Ano. |
| `Trimestre` | Trimestre do ano, de 1 a 4. |
| `Mês` | Nome do mês em minúsculas (janeiro, fevereiro...), ordenado pelo número do mês. |
| `Ano e mês` | Texto no formato AAAA-MM, bom para séries mensais em ordem. |
| `Número do mês` (oculta) | Mês de 1 a 12. |
| `Dia` (oculta) | Dia do mês. |

---

## Relationships

Todas saem de Despesas, de muitos para um, e filtram numa direção só.

| From | To | Cardinality | Cross-filter |
|---|---|---|---|
| `Despesas[parlamentar_id]` | `Parlamentares[parlamentar_id]` | many → one | singleDirection |
| `Despesas[categoria_id]` | `Categorias[categoria_id]` | many → one | singleDirection |
| `Despesas[uf]` | `Estados[UF]` | many → one | singleDirection |
| `Despesas[Data de competência]` | `'Calendário'[Data]` | many → one | singleDirection |

`Despesas[uf]` é o estado do parlamentar quando a despesa foi feita.
