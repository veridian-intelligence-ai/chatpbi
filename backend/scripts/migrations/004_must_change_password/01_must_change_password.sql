-- =========================================================================
-- 004_must_change_password / 01_must_change_password.sql
-- Força troca de senha no primeiro acesso (e em reset administrativo).
--
-- Flag por utilizador em auth.users. Quando TRUE, o backend obriga o
-- utilizador a definir uma nova password antes de aceder ao resto da app;
-- volta a FALSE após a troca bem-sucedida. Default FALSE para não afectar
-- os utilizadores existentes — só é posto a TRUE de forma explícita (ex.:
-- ao criar um utilizador com password temporária).
--
-- Idempotente: ADD COLUMN IF NOT EXISTS. Pode correr múltiplas vezes.
-- Espelha o run_auth_migrations() executado no arranque do auth_server.
-- =========================================================================

BEGIN;

ALTER TABLE auth.users
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN auth.users.must_change_password IS
    'TRUE obriga o utilizador a definir nova password no próximo login (primeiro acesso, password temporária ou reset por admin). Volta a FALSE após troca bem-sucedida.';

COMMIT;

-- =========================================================================
-- ROLLBACK:
-- BEGIN;
-- ALTER TABLE auth.users DROP COLUMN IF EXISTS must_change_password;
-- COMMIT;
-- =========================================================================
