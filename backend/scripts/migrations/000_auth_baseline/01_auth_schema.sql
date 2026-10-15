-- =========================================================================
-- 000_auth_baseline / 01_auth_schema.sql
-- Baseline do schema `auth` — fiel a produção (pg_dump 18.x, schema-only).
--
-- Objectivo: numa BD vazia, este script + 001_ai deixam o schema idêntico
-- a produção. É o passo 000 do bootstrap (auth é a raiz; vem antes do 001_ai
-- porque o schema `ai` não depende de `auth` ao nível de DDL, mas a ordem
-- lógica de tenancy é auth → ai → 002).
--
-- Idempotente: CREATE ... IF NOT EXISTS em tudo + DO-blocks com guard em
-- pg_constraint.conname para as FKs. Pode correr múltiplas vezes sem erro.
--
-- NOTA LEGACY: a tabela auth.conversation_history é resíduo legacy (a
-- história de conversas vive hoje no schema `ai`, tabela ai.chat_messages).
-- Mantém-se aqui para o baseline reflectir produção EXACTAMENTE. A sua
-- remoção será uma migração futura própria (003_cleanup), não uma omissão.
-- =========================================================================

BEGIN;

-- -------------------------------------------------------------------------
-- Schema
-- -------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS auth;

-- -------------------------------------------------------------------------
-- Tabelas (ordem de dependência: clients → users → restantes)
-- BIGSERIAL onde o dump de prod usa sequence + nextval (fiel ao prod).
-- FKs deferidas para o fim do ficheiro.
-- -------------------------------------------------------------------------

-- clients: raiz da hierarquia multi-tenant
CREATE TABLE IF NOT EXISTS auth.clients (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    slug        VARCHAR(100) NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- slug único a nível global (identificador estável do cliente)
    CONSTRAINT clients_slug_key UNIQUE (slug)
);

-- users: utilizadores, sempre pertencentes a um client
CREATE TABLE IF NOT EXISTS auth.users (
    id             BIGSERIAL PRIMARY KEY,
    client_id      BIGINT NOT NULL,
    email          VARCHAR(255) NOT NULL,
    password_hash  VARCHAR(255),
    full_name      VARCHAR(200),
    role           VARCHAR(50) NOT NULL DEFAULT 'user',
    status         VARCHAR(20) NOT NULL DEFAULT 'active',
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invited_by     BIGINT,
    invited_at     TIMESTAMPTZ,
    activated_at   TIMESTAMPTZ,

    CONSTRAINT users_role_check   CHECK (role IN ('admin', 'member')),
    CONSTRAINT users_status_check CHECK (status IN ('pending', 'active', 'suspended')),
    -- email único por cliente (o mesmo email pode existir em clients diferentes)
    CONSTRAINT users_email_per_client_unique UNIQUE (client_id, email)
);

COMMENT ON COLUMN auth.users.password_hash IS 'bcrypt hash. NULL se user só usa magic link.';
COMMENT ON COLUMN auth.users.role          IS 'admin: gere users do client, vê billing. member: usa o chat.';
COMMENT ON COLUMN auth.users.status        IS 'pending: convidado, ainda não fez primeiro login. active: operacional. suspended: bloqueado por admin.';
COMMENT ON COLUMN auth.users.invited_by    IS 'FK para o admin que enviou o convite. NULL se foi criado directamente (seed/dev).';
COMMENT ON COLUMN auth.users.invited_at    IS 'Quando o convite foi enviado.';
COMMENT ON COLUMN auth.users.activated_at  IS 'Primeiro login bem-sucedido (magic link clicado ou password definida).';

-- sessions: sessões autenticadas (JWT token persistido para validação)
CREATE TABLE IF NOT EXISTS auth.sessions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    token       VARCHAR(128) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    ip_address  INET,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at  TIMESTAMPTZ,

    -- token de sessão único (lookup directo no hot path de auth)
    CONSTRAINT sessions_token_key UNIQUE (token)
);

-- magic_link_tokens: tokens de uso único para login passwordless
CREATE TABLE IF NOT EXISTS auth.magic_link_tokens (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    token_hash  VARCHAR(128) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    ip_address  INET,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT magic_link_tokens_hash_unique UNIQUE (token_hash)
);

COMMENT ON TABLE  auth.magic_link_tokens            IS 'Tokens de uso único para login passwordless. TTL 15min, hash sha256.';
COMMENT ON COLUMN auth.magic_link_tokens.token_hash IS 'sha256(raw_token). O raw_token nunca é guardado em DB.';
COMMENT ON COLUMN auth.magic_link_tokens.used_at    IS 'Quando o token foi consumido. NULL = ainda válido (se não expirado).';
COMMENT ON COLUMN auth.magic_link_tokens.ip_address IS 'IP do request de consumo (auditoria).';

-- conversation_history: LEGACY (ver nota no cabeçalho). Candidata a drop em 003_cleanup.
-- Mantida fiel a produção para o baseline reflectir a BD real.
CREATE TABLE IF NOT EXISTS auth.conversation_history (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    session_id  VARCHAR(100) NOT NULL,
    module      VARCHAR(50) NOT NULL,
    role        VARCHAR(20) NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- invitations: convites por email (TTL 7 dias, token hash sha256)
CREATE TABLE IF NOT EXISTS auth.invitations (
    id          BIGSERIAL PRIMARY KEY,
    client_id   BIGINT NOT NULL,
    email       VARCHAR(255) NOT NULL,
    full_name   VARCHAR(200),
    role        VARCHAR(50) NOT NULL DEFAULT 'member',
    token_hash  VARCHAR(128) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    revoked_at  TIMESTAMPTZ,
    created_by  BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT invitations_role_check CHECK (role IN ('admin', 'member')),
    CONSTRAINT invitations_hash_unique UNIQUE (token_hash)
);

COMMENT ON TABLE  auth.invitations             IS 'Convites por email. TTL 7 dias. Token hash sha256.';
COMMENT ON COLUMN auth.invitations.role        IS 'Role que o user terá após aceitar (admin ou member).';
COMMENT ON COLUMN auth.invitations.token_hash  IS 'sha256(raw_token). O raw_token nunca é guardado em DB.';
COMMENT ON COLUMN auth.invitations.accepted_at IS 'Quando o convite foi aceite (user criado em auth.users).';
COMMENT ON COLUMN auth.invitations.revoked_at  IS 'Convite cancelado pelo admin antes de ser aceite.';

-- -------------------------------------------------------------------------
-- Índices (incluindo os parciais e o GIN sobre metadata)
-- -------------------------------------------------------------------------

-- clients
CREATE INDEX IF NOT EXISTS idx_clients_status ON auth.clients (status);

-- conversation_history (legacy)
CREATE INDEX IF NOT EXISTS idx_conv_created  ON auth.conversation_history (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_metadata ON auth.conversation_history USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_conv_session  ON auth.conversation_history (session_id);
CREATE INDEX IF NOT EXISTS idx_conv_user     ON auth.conversation_history (user_id);

-- invitations
CREATE INDEX IF NOT EXISTS idx_invitations_client  ON auth.invitations (client_id);
CREATE INDEX IF NOT EXISTS idx_invitations_email   ON auth.invitations (email);
CREATE INDEX IF NOT EXISTS idx_invitations_expires ON auth.invitations (expires_at);
-- Index parcial: só convites pendentes (não aceites, não revogados)
CREATE INDEX IF NOT EXISTS idx_invitations_pending
    ON auth.invitations (token_hash)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;

-- magic_link_tokens
CREATE INDEX IF NOT EXISTS idx_magic_link_tokens_user    ON auth.magic_link_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_magic_link_tokens_expires ON auth.magic_link_tokens (expires_at);
-- Index parcial: só tokens activos (não usados) — acelera o lookup do hot path
CREATE INDEX IF NOT EXISTS idx_magic_link_tokens_active
    ON auth.magic_link_tokens (token_hash)
    WHERE used_at IS NULL;

-- sessions
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON auth.sessions (expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_token   ON auth.sessions (token);
CREATE INDEX IF NOT EXISTS idx_sessions_user    ON auth.sessions (user_id);

-- users
CREATE INDEX IF NOT EXISTS idx_users_client ON auth.users (client_id);
CREATE INDEX IF NOT EXISTS idx_users_email  ON auth.users (email);
CREATE INDEX IF NOT EXISTS idx_users_status ON auth.users (status);

-- -------------------------------------------------------------------------
-- Foreign Keys (todas no fim, cada uma com guard idempotente).
-- O ON DELETE de cada FK é fiel ao dump de produção:
--   CASCADE      → users.client_id, sessions.user_id, magic_link_tokens.user_id,
--                  conversation_history.user_id, invitations.client_id
--   SET NULL     → users.invited_by (self-FK), invitations.created_by
-- -------------------------------------------------------------------------

-- users.client_id → clients(id)  [CASCADE]
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_client_id_fkey') THEN
        ALTER TABLE auth.users
            ADD CONSTRAINT users_client_id_fkey
            FOREIGN KEY (client_id) REFERENCES auth.clients(id) ON DELETE CASCADE;
    END IF;
END $$;

-- users.invited_by → users(id)  [SET NULL]  — self-FK
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_invited_by_fkey') THEN
        ALTER TABLE auth.users
            ADD CONSTRAINT users_invited_by_fkey
            FOREIGN KEY (invited_by) REFERENCES auth.users(id) ON DELETE SET NULL;
    END IF;
END $$;

-- sessions.user_id → users(id)  [CASCADE]
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sessions_user_id_fkey') THEN
        ALTER TABLE auth.sessions
            ADD CONSTRAINT sessions_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
END $$;

-- magic_link_tokens.user_id → users(id)  [CASCADE]
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'magic_link_tokens_user_id_fkey') THEN
        ALTER TABLE auth.magic_link_tokens
            ADD CONSTRAINT magic_link_tokens_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
END $$;

-- conversation_history.user_id → users(id)  [CASCADE]  (legacy)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'conversation_history_user_id_fkey') THEN
        ALTER TABLE auth.conversation_history
            ADD CONSTRAINT conversation_history_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
END $$;

-- invitations.client_id → clients(id)  [CASCADE]
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'invitations_client_id_fkey') THEN
        ALTER TABLE auth.invitations
            ADD CONSTRAINT invitations_client_id_fkey
            FOREIGN KEY (client_id) REFERENCES auth.clients(id) ON DELETE CASCADE;
    END IF;
END $$;

-- invitations.created_by → users(id)  [SET NULL]
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'invitations_created_by_fkey') THEN
        ALTER TABLE auth.invitations
            ADD CONSTRAINT invitations_created_by_fkey
            FOREIGN KEY (created_by) REFERENCES auth.users(id) ON DELETE SET NULL;
    END IF;
END $$;

COMMIT;

-- =========================================================================
-- ROLLBACK (drop completo do schema auth — destrói TODOS os dados):
-- BEGIN;
-- DROP SCHEMA IF EXISTS auth CASCADE;
-- COMMIT;
-- =========================================================================
