# Backend: API e login (Python, FastAPI)

Complementa o CLAUDE.md da raiz. API em Python (FastAPI), com o modelo semântico num pacote em `api/semantic_models/`.

## Dois serviços, uma imagem

O mesmo `Dockerfile` serve os dois serviços do Railway, com start commands diferentes:

| Serviço no Railway | Processo | Start command | Healthcheck |
|---|---|---|---|
| `backend` (API) | `api/main.py` | CMD do Dockerfile (`uvicorn main:app` a partir de `/app/api`) | `/health` |
| `auth` (login) | `auth_server.py` | `sh -c 'cd /app && uvicorn auth_server:app --host 0.0.0.0 --port ${PORT:-8080}'` | `/health` |

- `api/main.py`: chat (`/chat/v2`), voz (`/chat/voice`, `/voice/*`, `/stt`, `/tts`), sugestões e histórico das conversas.
- `auth_server.py`: login headless pelo WorkOS (`/auth/workos/password-login`, `forgot-password`, `reset-password`), sessão opaca em `auth.sessions`, `/auth/me`, `/auth/logout` e os endpoints `/admin/*`.
- Os dois usam o mesmo Postgres, cada um com o próprio pool de conexões (`DB_POOL_MAX` somado tem de caber no limite do Postgres).

## Regras da API

- Todo endpoint, menos `GET /health`, pede `Authorization: Bearer <token>`. `get_current_user()` valida o token em `auth.sessions`.
- `check_session_owner()` isola as conversas por usuário e cliente.
- Os endpoints que custam API (`/chat/v2`, `/chat/voice`, `/voice/realtime/session`) passam por `check_rate_limit()`: 20 por minuto e 300 por hora por usuário.
- Endpoints com I/O bloqueante (psycopg2, Anthropic, Power BI) são `def` síncronos. Só `/stt` e `/tts` são `async`.
- `MODULE = "fabric"` fica fixo e vai em toda chamada ao `ConversationStore`.

## Regras do login

- O login é do WorkOS, sem redirecionar: a tela do app manda e-mail e senha para `/auth/workos/password-login`. Só entra quem existe no WorkOS com e-mail verificado e está em `auth.users` (403 `workos_user_not_provisioned` se não estiver).
- Instalação nova: com `SEED_ADMIN_EMAIL`, o arranque cria o cliente `SEED_CLIENT_SLUG` e esse usuário como admin ativo (idempotente).
- `AUTH_SECRET_KEY` é opcional. Sem ela, os endpoints `/admin/*` ficam desligados (403).
- `API_PUBLIC_URL` é opcional (o nome antigo, `VERIDIAN_API_URL`, continua valendo): o login devolve esse endereço como `api_url`, mas o frontend usa primeiro o `VITE_API_BASE_URL` do build.
- O link do e-mail de troca de senha é o "Password reset URL" do WorkOS (`https://<frontend>/reset-password`).
- `GET /auth/workos/login` e `POST /auth/workos/callback` (página do AuthKit) continuam no código, sem uso pela tela.

## Banco

- Esquemas `auth` (clientes, usuários, sessões) e `ai` (conversas, mensagens, estado, eventos de uso e de rate limit).
- Numa base vazia, `db_bootstrap.ensure_baseline_schema()` roda os scripts de `scripts/migrations/` (000 e 001) sob advisory lock. Depois, `run_migrations()` e `run_auth_migrations()` aplicam o DDL idempotente.
- Mudança de esquema em produção só com aprovação do autor.

## Modelo semântico

- `SEMANTIC_MODEL` escolhe o pacote em `api/semantic_models/<nome>/` (padrão `cota_parlamentar`).
- Cada pacote tem `SEMANTIC_MODEL.md` (medidas, glossário, regras, perguntas-tipo), `MODEL_SCHEMA.md` (tabelas e relações), `dax_examples.md` (DAX validado) e `__init__.py` (nome, fuso, moeda, regras fundamentais, exemplos de voz, sugestões, rótulos dos visuais).
- `api/prompts_fabric.py` monta o prompt com cache a partir do pacote. Mudou o pacote, sobe o `PROMPT_VERSION`.
- Exemplo de DAX novo só entra depois de rodar no modelo.
- Todo número que o app mostra sai de uma consulta ao modelo.

## Power BI

- `api/adapters/fabric/`: token do service principal (client credentials) e a API Execute Queries.
- Variáveis: `FABRIC_TENANT_ID`, `FABRIC_CLIENT_ID`, `FABRIC_CLIENT_SECRET`, `FABRIC_WORKSPACE_ID`, `FABRIC_DEFAULT_DATASET_ID`.
- Modelo em Direct Lake: a fonte precisa de identidade fixa (conexão de nuvem sem SSO), senão o service principal leva 401 (skill `conexao-power-bi`).

## Voz

- Com `OPENAI_API_KEY`, a voz é ao vivo pela OpenAI Realtime (`api/realtime_voice.py`): `POST /voice/realtime/session` devolve uma chave efêmera com a sessão já configurada (modelo, voz, instruções e a ferramenta `consultar_dados`). O browser fala com a OpenAI por WebRTC.
- Os números da voz continuam vindo do `/chat/voice`: quando o modelo de voz chama `consultar_dados`, o frontend manda a pergunta ao `/chat/voice` e devolve a resposta como resultado da ferramenta.
- Sem `OPENAI_API_KEY`, a voz clássica usa `/stt` e `/tts` da ElevenLabs (`ELEVENLABS_API_KEY`).
- O assistente se apresenta com o nome de `ASSISTANT_NAME` (padrão ChatPBI), no chat e na voz.
- `GET /voice/config` diz ao frontend quais vozes estão ligadas.

## Orquestrador

- `api/orchestrator.py` (`DAXConversationOrchestrator`): Claude → `execute_dax` → Power BI → Claude, até 6 iterações, 50 linhas por resultado.
- O teto de tokens é por chamada (`ANTHROPIC_MAX_TOKENS`, padrão 12000). `ANTHROPIC_TIMEOUT_SECONDS` (padrão 180) tem de ficar acima de `ANTHROPIC_MAX_TOKENS / ~85`.
- A voz usa o mesmo orquestrador com o modelo da voz (`ANTHROPIC_VOICE_MODEL`) e um bloco de instruções de voz.

## Testes e lint

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ruff check .
pytest
```

Os testes não chamam o Power BI, o Claude, a OpenAI, a ElevenLabs nem o WorkOS de verdade.

## Rodar local

```bash
# Terminal 1, login (lê auth.env)
uvicorn auth_server:app --reload --port 8080
# Terminal 2, API (lê .env)
cd api && uvicorn main:app --reload --port 8000
```

## Cuidados

1. `main.py` insere a pasta pai no `sys.path` para importar `cors_config` e `db_bootstrap` rodando de `/app/api`.
2. O `COPY` do Dockerfile é seletivo: arquivo novo na raiz precisa de um `COPY` próprio.
3. `ALLOWED_ORIGINS` é obrigatória (fail-fast).
4. No Railway, ajuste as variáveis antes de subir o código que depende delas.
5. Nenhum segredo entra no Git: os valores ficam nas variáveis de cada serviço no Railway.
