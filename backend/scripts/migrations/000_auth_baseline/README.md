# 000_auth_baseline

Baseline do schema **`auth`**, fiel a produção (origem: `pg_dump` 18.x, schema-only).

## Contexto

O schema `auth` é a **raiz** do modelo multi-tenant da Veridian: `clients` →
`users` → (`sessions`, `magic_link_tokens`, `invitations`, ...). Esta migração
recria esse schema do zero numa BD vazia, de forma **idempotente**.

Foi extraída a partir do dump `auth_baseline_prod.sql` (na raiz do repo, temporário)
e convertida para o estilo das migrações do projecto:

- `BEGIN; ... COMMIT;` transaccional
- `CREATE SCHEMA / TABLE / INDEX ... IF NOT EXISTS`
- `BIGSERIAL` onde o dump usava `sequence + nextval` (equivalente, fiel ao prod)
- PKs e `CHECK`s inline; FKs no fim, cada uma com guard idempotente em `pg_constraint.conname`
- bloco de `ROLLBACK` em comentário no fim do `.sql`

## Conteúdo

`01_auth_schema.sql` cria:

| Tabela | Notas |
|---|---|
| `clients` | raiz multi-tenant; `slug` único |
| `users` | FK `client_id` → `clients`; self-FK `invited_by`; CHECKs em `role`/`status` |
| `sessions` | FK `user_id` → `users`; `token` único |
| `magic_link_tokens` | FK `user_id` → `users`; login passwordless (TTL 15min) |
| `invitations` | FK `client_id` → `clients`, `created_by` → `users`; convites (TTL 7 dias) |
| `conversation_history` | **LEGACY** — ver abaixo |

Inclui todos os índices de produção (incl. os parciais e o GIN sobre
`conversation_history.metadata`) e as 7 FKs com o `ON DELETE` exacto do prod
(`CASCADE` na maioria; `SET NULL` em `users.invited_by` e `invitations.created_by`).

## ⚠️ `conversation_history` é legacy

A tabela `auth.conversation_history` é **resíduo legacy**. A história de conversas
vive hoje no schema `ai` (tabela `ai.chat_messages`); confirmou-se que esta tabela
**não é lida nem escrita** em lado nenhum do código (`api/` e `auth_server.py`).

Mantém-se aqui **de propósito**: o baseline tem de reflectir produção
*exactamente*, para que uma BD nova fique idêntica à BD real. A sua remoção será
uma migração futura própria — **`003_cleanup`** — e não uma omissão silenciosa
neste baseline.

## Dívida conhecida (para `003_cleanup`)

Itens preservados **fiéis a produção** neste baseline, a corrigir numa migração
futura própria (`003_cleanup`) — **não** alterar aqui:

1. **`conversation_history` legacy** — tabela + sequência + 4 índices + FK. Não é
   lida nem escrita pelo código (a história vive em `ai.chat_messages`). Candidata
   a `DROP` (ver secção acima).

2. **Quirk `users.role`** — a coluna tem `DEFAULT 'user'` (fiel ao dump), mas o
   `users_role_check` só permite `'admin'`/`'member'`. Em produção, um `INSERT` em
   `auth.users` **sem** `role` explícita **viola o CHECK e falha**. É uma
   inconsistência latente do prod, preservada tal e qual. Cleanup: alinhar o
   default (ex.: `'member'`) com o CHECK.

3. **Comentários desatualizados vs backend real:**
   - Os `COMMENT ON` de `auth.magic_link_tokens` (TABLE: *"login passwordless... hash
     sha256"*; coluna `token_hash`: *"sha256(raw_token)"*) vêm **verbatim do dump**,
     mas o backend real usa **bcrypt** (cost 12) para passwords e **tokens opacos**
     via `secrets.token_urlsafe(48)` para sessões — não sha256. Os comentários são
     metadados de produção desatualizados.
   - Nota: o `auth.sessions` **não tem** `COMMENT ON` no dump. O comentário inline
     `-- sessions: ... (JWT token...)` neste `.sql` foi escrito por nós e está
     **factualmente errado** (a sessão usa token opaco `secrets.token_urlsafe(48)`,
     não JWT). Corrigir esse comentário no cleanup também.

## Ordem de bootstrap

Numa BD vazia, aplicar por ordem:

```
000_auth_baseline   →   001_ai   →   002_multi_tenant_foundation
```

- **000** (este) — schema `auth` completo
- **001_ai** — schema `ai` (baseline, a partir de `ai_baseline_prod.sql`)
- **002** — fundação multi-tenant (alters/seeds já existentes)

**000_auth_baseline + 001_ai juntos** tornam uma BD vazia **idêntica a produção**
ao nível de schema. O 002 assenta por cima com os ALTERs e seeds de tenancy.

## Como aplicar (manual, sob aprovação)

```bash
psql "$DATABASE_URL" -f scripts/migrations/000_auth_baseline/01_auth_schema.sql
```

Idempotente: pode correr múltiplas vezes sem erro. Para reverter (⚠️ destrói
todos os dados de `auth`), usar o bloco `ROLLBACK` comentado no fim do `.sql`.
