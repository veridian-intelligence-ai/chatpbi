-- =========================================================================
-- 001_ai_baseline / 01_ai_schema.sql
-- Baseline do schema `ai` — fiel a produção (pg_dump 18.x, schema-only).
--
-- Objectivo: numa BD vazia, 000_auth_baseline + este script deixam o schema
-- idêntico a produção. É o passo 001 do bootstrap.
--
-- DEPENDÊNCIA: a FK chat_sessions_client_id_fkey referencia auth.clients(id).
-- Por isso este script TEM de correr DEPOIS do 000_auth_baseline (o schema
-- `auth` e a tabela auth.clients têm de existir primeiro).
--
-- Idempotente: CREATE ... IF NOT EXISTS em tudo + DO-blocks com guard em
-- pg_constraint.conname para as FKs. Pode correr múltiplas vezes sem erro.
--
-- NOTA: o default module='finance' é resíduo da era Lovable (módulos
-- finance/sales legados). Hoje o backend usa module='fabric' (hardcoded em
-- main.py). Preservado fiel ao prod — limpeza prevista para 003_cleanup.
-- =========================================================================

BEGIN;

-- -------------------------------------------------------------------------
-- Schema
-- -------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS ai;

COMMENT ON SCHEMA ai IS 'Schema do histórico de conversas e estado conversacional Veridian';

-- -------------------------------------------------------------------------
-- Tabelas (ordem de dependência: chat_sessions é referenciada pelas FKs
-- de chat_messages e chat_state). BIGSERIAL só em chat_messages.message_id
-- (única coluna com sequence+nextval no dump). FKs deferidas para o fim.
-- -------------------------------------------------------------------------

-- chat_sessions: sessões de chat (PK = session_id, UUID gerado pelo frontend)
CREATE TABLE IF NOT EXISTS ai.chat_sessions (
    session_id                 VARCHAR(100) PRIMARY KEY,
    module                     VARCHAR(50) NOT NULL DEFAULT 'finance',
    is_active                  BOOLEAN NOT NULL DEFAULT true,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_user_message_at       TIMESTAMPTZ,
    last_assistant_message_at  TIMESTAMPTZ,
    title                      TEXT,
    user_id                    INTEGER,          -- fiel ao prod: INTEGER (não bigint); sem FK no dump
    client_id                  BIGINT NOT NULL
);

COMMENT ON TABLE  ai.chat_sessions            IS 'Sessões de chat agrupadas por session_id e module';
COMMENT ON COLUMN ai.chat_sessions.session_id IS 'UUID gerado pelo frontend, identifica unicamente a conversa';
COMMENT ON COLUMN ai.chat_sessions.module     IS 'Módulo: finance, sales (default finance, extensível)';
COMMENT ON COLUMN ai.chat_sessions.is_active  IS 'TRUE = sessão visível, FALSE = arquivada/limpa';
COMMENT ON COLUMN ai.chat_sessions.client_id  IS 'Tenant isolation directo. Evita JOIN em queries de admin portal.';

-- chat_messages: mensagens individuais user/assistant, ordenadas por sessão
CREATE TABLE IF NOT EXISTS ai.chat_messages (
    message_id     BIGSERIAL PRIMARY KEY,
    session_id     VARCHAR(100) NOT NULL,
    module         VARCHAR(50) NOT NULL DEFAULT 'finance',
    role           VARCHAR(20) NOT NULL,
    content        TEXT NOT NULL,
    message_order  INTEGER NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_chat_messages_role CHECK (role IN ('user', 'assistant'))
);

COMMENT ON TABLE  ai.chat_messages               IS 'Mensagens individuais user/assistant ordenadas';
COMMENT ON COLUMN ai.chat_messages.role          IS 'user ou assistant (CHECK constraint força isto)';
COMMENT ON COLUMN ai.chat_messages.content       IS 'Conteúdo da mensagem, plain text ou JSON serializado';
COMMENT ON COLUMN ai.chat_messages.message_order IS 'Ordem da mensagem na sessão (1, 2, 3, ...)';

-- chat_state: estado conversacional por sessão (1 linha por session_id)
CREATE TABLE IF NOT EXISTS ai.chat_state (
    session_id  VARCHAR(100) PRIMARY KEY,
    module      VARCHAR(50) NOT NULL DEFAULT 'finance',
    state_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  ai.chat_state            IS 'Estado conversacional por sessão (active_domain, filters, dimensões)';
COMMENT ON COLUMN ai.chat_state.state_json IS 'JSONB com state conversacional. Indexado via GIN.';

-- -------------------------------------------------------------------------
-- Índices (incluindo o parcial WHERE is_active e o GIN sobre state_json)
-- -------------------------------------------------------------------------

-- chat_messages
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON ai.chat_messages (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_order   ON ai.chat_messages (session_id, module, message_order DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON ai.chat_messages (session_id, module);

-- chat_sessions
-- Index parcial: só sessões activas — acelera a listagem da sidebar
CREATE INDEX IF NOT EXISTS idx_chat_sessions_active
    ON ai.chat_sessions (is_active)
    WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_chat_sessions_client      ON ai.chat_sessions (client_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_client_user ON ai.chat_sessions (client_id, user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_module      ON ai.chat_sessions (module);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated     ON ai.chat_sessions (updated_at DESC);

-- chat_state
CREATE INDEX IF NOT EXISTS idx_chat_state_json   ON ai.chat_state USING gin (state_json);
CREATE INDEX IF NOT EXISTS idx_chat_state_module ON ai.chat_state (module);

-- -------------------------------------------------------------------------
-- Foreign Keys (todas no fim, cada uma com guard idempotente).
-- ON DELETE fiel ao dump de produção (as 3 são CASCADE).
-- NOTA: chat_sessions_client_id_fkey depende de auth.clients (schema auth,
-- criado em 000_auth_baseline).
-- -------------------------------------------------------------------------

-- chat_messages.session_id → chat_sessions(session_id)  [CASCADE]
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chat_messages_session_id_fkey') THEN
        ALTER TABLE ai.chat_messages
            ADD CONSTRAINT chat_messages_session_id_fkey
            FOREIGN KEY (session_id) REFERENCES ai.chat_sessions(session_id) ON DELETE CASCADE;
    END IF;
END $$;

-- chat_sessions.client_id → auth.clients(id)  [CASCADE]  (cross-schema → auth)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chat_sessions_client_id_fkey') THEN
        ALTER TABLE ai.chat_sessions
            ADD CONSTRAINT chat_sessions_client_id_fkey
            FOREIGN KEY (client_id) REFERENCES auth.clients(id) ON DELETE CASCADE;
    END IF;
END $$;

-- chat_state.session_id → chat_sessions(session_id)  [CASCADE]
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chat_state_session_id_fkey') THEN
        ALTER TABLE ai.chat_state
            ADD CONSTRAINT chat_state_session_id_fkey
            FOREIGN KEY (session_id) REFERENCES ai.chat_sessions(session_id) ON DELETE CASCADE;
    END IF;
END $$;

COMMIT;

-- =========================================================================
-- ROLLBACK (drop completo do schema ai — destrói TODOS os dados):
-- BEGIN;
-- DROP SCHEMA IF EXISTS ai CASCADE;
-- COMMIT;
-- =========================================================================
