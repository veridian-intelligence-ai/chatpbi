-- =========================================================================
-- 005_usage_events / 01_usage_events.sql
-- Instrumentação base de consumo (Tarefa O.1) — fundação da Fase A do portal
-- de administração interno (consumo de tokens / custos por cliente e
-- utilizador).
--
-- Um evento por chamada PAGA, com UNIDADES FÍSICAS apenas:
--   - Claude (provider='anthropic'): input/output/cache tokens, por /chat/v2
--     e /chat/voice.
--   - ElevenLabs (provider='elevenlabs'): char_count (TTS e STT) e audio_bytes
--     (STT), por /tts e /stt.
-- Pricing e cálculo de custo (€) ficam para O.2 — esta tabela NÃO guarda €.
--
-- Tabela NOVA e separada de ai.api_usage_events (que é hot-path do rate
-- limiter, com outro shape — não é tocada).
--
-- Emissão: ponto único conversation_store.emit_usage_event(), best-effort
-- (nunca derruba um pedido pago já bem-sucedido).
--
-- Idempotente: CREATE ... IF NOT EXISTS. Pode correr múltiplas vezes.
-- Espelha o run_migrations() (api/conversation_store.py) executado no arranque
-- do serviço api.
--
-- FOLLOW-UP: sem particionamento por agora (volume baixo); rever quando o
-- volume crescer (ex.: particionar por mês sobre created_at).
-- =========================================================================

BEGIN;

-- usage_events: uma linha por chamada paga (Claude ou ElevenLabs).
CREATE TABLE IF NOT EXISTS ai.usage_events (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_id           BIGINT NOT NULL,
    user_id             BIGINT NOT NULL,
    session_id          VARCHAR(100),
    endpoint            TEXT NOT NULL,
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    input_tokens        BIGINT,
    output_tokens       BIGINT,
    cache_read_tokens   BIGINT,
    cache_write_tokens  BIGINT,
    char_count          BIGINT,
    audio_bytes         BIGINT,
    latency_ms          INTEGER,
    iteration_count     INTEGER,
    status              TEXT NOT NULL
);

COMMENT ON TABLE  ai.usage_events                    IS 'Eventos de consumo (O.1): unidades físicas por chamada paga. Custo (€) é derivado em O.2 — não materializado aqui.';
COMMENT ON COLUMN ai.usage_events.client_id          IS 'Tenant (auth.clients.id). Sem FK — eventos sobrevivem a remoções para fins de auditoria/consumo.';
COMMENT ON COLUMN ai.usage_events.user_id            IS 'Utilizador (auth.users.id) que originou a chamada.';
COMMENT ON COLUMN ai.usage_events.session_id         IS 'Sessão de chat (ai.chat_sessions.session_id) quando aplicável; NULL para /tts e /stt.';
COMMENT ON COLUMN ai.usage_events.endpoint           IS 'Endpoint emissor: /chat/v2, /chat/voice, /tts, /stt.';
COMMENT ON COLUMN ai.usage_events.provider           IS 'anthropic | elevenlabs.';
COMMENT ON COLUMN ai.usage_events.model              IS 'Modelo/voz usado (ex.: claude-sonnet-4-5, claude-haiku-4-5-..., eleven_multilingual_v2, scribe_v1).';
COMMENT ON COLUMN ai.usage_events.input_tokens       IS 'Tokens de input Claude (soma das iterações do turno). NULL para ElevenLabs.';
COMMENT ON COLUMN ai.usage_events.output_tokens      IS 'Tokens de output Claude (soma das iterações). NULL para ElevenLabs.';
COMMENT ON COLUMN ai.usage_events.cache_read_tokens  IS 'Tokens lidos da cache de prompt (Claude). NULL para ElevenLabs.';
COMMENT ON COLUMN ai.usage_events.cache_write_tokens IS 'Tokens escritos na cache de prompt (Claude). NULL para ElevenLabs.';
COMMENT ON COLUMN ai.usage_events.char_count         IS 'Caracteres ElevenLabs: TTS = texto enviado (limpo/truncado); STT = texto transcrito. NULL para Claude.';
COMMENT ON COLUMN ai.usage_events.audio_bytes        IS 'STT: bytes do áudio de entrada (proxy). A duração real (minutos) é follow-up. NULL para os restantes.';
COMMENT ON COLUMN ai.usage_events.latency_ms         IS 'Latência do provider no turno (ms). Claude: soma das iterações.';
COMMENT ON COLUMN ai.usage_events.iteration_count    IS 'Nº de iterações Claude→Fabric no turno. NULL para ElevenLabs.';
COMMENT ON COLUMN ai.usage_events.status             IS 'success | error (resultado do turno; o consumo conta mesmo em erro).';

-- Índices alinhados às queries do admin portal: consumo por cliente / por
-- utilizador ao longo do tempo.
CREATE INDEX IF NOT EXISTS idx_usage_events_client_time
    ON ai.usage_events (client_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_events_user_time
    ON ai.usage_events (user_id, created_at);

COMMIT;

-- =========================================================================
-- ROLLBACK:
-- BEGIN;
-- DROP TABLE IF EXISTS ai.usage_events;
-- COMMIT;
-- =========================================================================
