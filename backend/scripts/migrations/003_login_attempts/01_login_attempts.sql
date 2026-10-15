-- =========================================================================
-- 003_login_attempts / 01_login_attempts.sql
-- Tabela de auditoria de tentativas de login para lockout anti-brute-force
-- (Tarefa I.12).
--
-- Estado em Postgres (não em memória): tem de sobreviver a reinícios e
-- funcionar com múltiplas instâncias do auth_server.
--
-- Política aplicada no código (auth_server.login):
--   >= 5 tentativas FALHADAS para a mesma combinação (email + ip_address)
--   numa janela de 15 minutos → HTTP 429 antes de verificar a password.
--   A janela deslizante de 15 min limpa-se naturalmente (sem job de purga).
--
-- Idempotente: CREATE ... IF NOT EXISTS. Pode correr múltiplas vezes.
-- Espelha o run_auth_migrations() executado no arranque do auth_server.
-- =========================================================================

BEGIN;

-- login_attempts: uma linha por tentativa de login (falhada E bem-sucedida)
CREATE TABLE IF NOT EXISTS auth.login_attempts (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL,
    ip_address    INET,
    success       BOOLEAN NOT NULL DEFAULT FALSE,
    attempted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  auth.login_attempts            IS 'Auditoria de tentativas de login para lockout (email+IP, 5 falhas / 15 min).';
COMMENT ON COLUMN auth.login_attempts.email      IS 'Email tentado (texto cru, mesmo que o user não exista — evita enumeração).';
COMMENT ON COLUMN auth.login_attempts.ip_address IS 'IP real do cliente (CF-Connecting-IP, atrás do Cloudflare). NULL se indeterminável.';
COMMENT ON COLUMN auth.login_attempts.success    IS 'TRUE se a tentativa autenticou com sucesso, FALSE caso contrário.';

-- Índice para a query de contagem do lockout: filtra por email+ip e janela temporal.
CREATE INDEX IF NOT EXISTS idx_login_attempts_lookup
    ON auth.login_attempts (email, ip_address, attempted_at);

COMMIT;

-- =========================================================================
-- ROLLBACK:
-- BEGIN;
-- DROP TABLE IF EXISTS auth.login_attempts;
-- COMMIT;
-- =========================================================================
