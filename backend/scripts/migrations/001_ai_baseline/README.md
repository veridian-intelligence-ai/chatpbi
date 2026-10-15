# 001_ai_baseline

Baseline do schema **`ai`**, fiel a produção (origem: `pg_dump` 18.x, schema-only).

## Contexto

O schema `ai` guarda o **histórico de conversas e o estado conversacional** da
Veridian: `chat_sessions` (1 linha por conversa), `chat_messages` (mensagens
ordenadas user/assistant) e `chat_state` (estado JSONB por sessão). É aqui que
vive a história real do chat — não na tabela legacy `auth.conversation_history`.

Foi extraída a partir do dump `ai_baseline_prod.sql` (na raiz do repo, temporário)
e convertida para o estilo das migrações do projecto:

- `BEGIN; ... COMMIT;` transaccional
- `CREATE SCHEMA / TABLE / INDEX ... IF NOT EXISTS`
- `BIGSERIAL` em `chat_messages.message_id` (única coluna com `sequence + nextval`
  no dump; `session_id` é a PK das outras duas tabelas, um UUID varchar do frontend)
- PKs e `CHECK` inline; FKs no fim, cada uma com guard idempotente em `pg_constraint.conname`
- bloco de `ROLLBACK` em comentário no fim do `.sql`

## Conteúdo

`01_ai_schema.sql` cria:

| Tabela | Notas |
|---|---|
| `chat_sessions` | PK `session_id` (UUID); FK `client_id` → **`auth.clients`**; `user_id` é `INTEGER` |
| `chat_messages` | PK `message_id` (`BIGSERIAL`); FK `session_id` → `chat_sessions`; CHECK `role IN (user,assistant)` |
| `chat_state` | PK `session_id`; FK `session_id` → `chat_sessions`; `state_json` JSONB default `{}` |

Inclui os **10 índices** de produção (incl. o parcial `idx_chat_sessions_active`
`WHERE is_active = true` e o GIN `idx_chat_state_json` sobre `state_json`), o
`COMMENT ON SCHEMA ai` e os 11 `COMMENT ON` de tabelas/colunas, e as **3 FKs**
(todas `ON DELETE CASCADE`).

## Dependência cross-schema (IMPORTANTE)

A FK **`chat_sessions_client_id_fkey`** referencia **`auth.clients(id)`**. Por isso
este script **só corre depois do `000_auth_baseline`** — o schema `auth` e a tabela
`auth.clients` têm de existir primeiro. As outras 2 FKs são internas ao schema `ai`.

## Ordem de bootstrap

Numa BD vazia, aplicar por ordem:

```
000_auth_baseline   →   001_ai_baseline   →   002_multi_tenant_foundation
```

- **000_auth_baseline** — schema `auth` completo (raiz; `auth.clients` é pré-requisito desta migração)
- **001_ai_baseline** (este) — schema `ai` completo
- **002** — fundação multi-tenant (alters/seeds já existentes)

**000_auth_baseline + 001_ai_baseline juntos** tornam uma BD vazia **idêntica a
produção** ao nível de schema. O 002 assenta por cima com os ALTERs e seeds de tenancy.

## Dívida conhecida (para `003_cleanup`)

Item preservado **fiel a produção** neste baseline, a corrigir numa migração futura
própria (`003_cleanup`) — **não** alterar aqui:

1. **Default `module = 'finance'`** — as 3 tabelas (`chat_sessions`, `chat_messages`,
   `chat_state`) têm `module VARCHAR(50) NOT NULL DEFAULT 'finance'`. É **resíduo da
   era Lovable** (módulos `finance`/`sales` legados). O backend real hoje usa
   `module = 'fabric'` (hardcoded em `api/main.py`), e o `COMMENT ON` da coluna ainda
   diz *"finance, sales"*. Sessões legadas em prod têm `module='finance'`/`'sales'`.
   Preservado tal e qual para fidelidade. Cleanup: alinhar default/comentário para
   `'fabric'` (ou tornar o módulo explícito sem default).

## Como aplicar (manual, sob aprovação)

```bash
# Pré-requisito: 000_auth_baseline já aplicado (auth.clients existe)
psql "$DATABASE_URL" -f scripts/migrations/001_ai_baseline/01_ai_schema.sql
```

Idempotente: pode correr múltiplas vezes sem erro. Para reverter (⚠️ destrói
todos os dados de `ai`), usar o bloco `ROLLBACK` comentado no fim do `.sql`.
