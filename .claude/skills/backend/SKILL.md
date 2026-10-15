---
name: backend
description: Monta e publica o backend do app no Railway (Python e FastAPI, pasta backend, dois serviços da mesma imagem: API e login), com o Postgres, as variáveis, os domínios e as conferências, e liga o app a outro modelo semântico. Use quando for publicar o backend, mudar uma variável, trocar o modelo ou investigar resposta errada do chat ou da voz.
---

# Backend no Railway

O backend fica em `backend/` e é a ponte com os dados. Um só `Dockerfile` serve dois serviços: a API (`api/main.py`: chat, voz, sugestões, histórico) e o login (`auth_server.py`: WorkOS e sessões). Detalhes em `backend/CLAUDE.md`.

## Antes de começar

- A conexão com o Power BI está pronta (skill `conexao-power-bi`), com os ids anotados.
- O repositório está no GitHub e o Railway tem acesso a ele (skill `repositorio`).
- A pessoa tem uma chave da API do Claude (platform.claude.com). Para a voz ao vivo, uma chave da API da OpenAI.

## Passo a passo (pelo conector do Railway)

1. **Projeto e Postgres.** Criar o projeto `app-chat-power-bi` e subir o template `postgres`.
2. **Serviço `backend` (API).** A partir do repositório, branch `main`, diretório raiz `/backend`. O Railway usa o `Dockerfile` (o CMD sobe a API). Healthcheck `/health`. Gerar o domínio público.
3. **Variáveis da API sem segredo** (a IA define):
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `ALLOWED_ORIGINS`: o domínio do frontend e `http://localhost:8080`.
   - `POWERBI_TENANT_ID`, `POWERBI_CLIENT_ID`, `POWERBI_WORKSPACE_ID`, `POWERBI_DATASET_ID` (ids).
   - O código lê os nomes `FABRIC_*`, que apontam para os de cima: `FABRIC_TENANT_ID=${{POWERBI_TENANT_ID}}`, `FABRIC_CLIENT_ID=${{POWERBI_CLIENT_ID}}`, `FABRIC_CLIENT_SECRET=${{POWERBI_CLIENT_SECRET}}`, `FABRIC_WORKSPACE_ID=${{POWERBI_WORKSPACE_ID}}`, `FABRIC_DEFAULT_DATASET_ID=${{POWERBI_DATASET_ID}}`.
   - `SEMANTIC_MODEL` (pacote do modelo em `api/semantic_models/`), `ANTHROPIC_MODEL=claude-sonnet-5-5`, `ANTHROPIC_VOICE_MODEL=claude-haiku-5-5`.
4. **Segredos da API** (a pessoa cola no painel do Railway, em Variables do serviço): `POWERBI_CLIENT_SECRET`, `ANTHROPIC_API_KEY` e `OPENAI_API_KEY` (voz ao vivo). A voz clássica, opcional, usa `ELEVENLABS_API_KEY`.
5. **Serviço `auth` (login).** Mesmo repositório e diretório raiz `/backend`, com o start command `sh -c 'cd /app && uvicorn auth_server:app --host 0.0.0.0 --port ${PORT:-8080}'`, healthcheck `/health`, `PORT=8080` e domínio público na porta 8080.
6. **Variáveis do login sem segredo:** `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `ALLOWED_ORIGINS`, `WORKOS_CLIENT_ID`, `API_PUBLIC_URL` (opcional: endereço público da API, devolvido no login; o frontend usa primeiro o `VITE_API_BASE_URL`; o nome antigo `VERIDIAN_API_URL` continua valendo) e o admin inicial: `SEED_CLIENT_SLUG`, `SEED_CLIENT_NAME`, `SEED_ADMIN_EMAIL`, `SEED_ADMIN_NAME`.
7. **Segredo do login** (a pessoa cola): `WORKOS_API_KEY`. `AUTH_SECRET_KEY` é opcional e só liga os endpoints `/admin/*`.
8. **Conferir:** `GET /health` nos dois serviços; entrar no app; uma pergunta no chat com visual; a voz ao vivo. O roteiro `scripts/smoke_chat_v2.py` confere a API com o token de uma sessão.

O primeiro arranque numa base vazia cria os esquemas `auth` e `ai` (`db_bootstrap.py`) e o admin das `SEED_*`.

## Ligar o app a outro modelo semântico

1. Crie o pacote `api/semantic_models/<modelo>/` copiando o de um modelo existente.
2. `SEMANTIC_MODEL.md`: cada medida, o glossário (termo do negócio → tabela, coluna ou medida), as regras que mudam a resposta e as perguntas-tipo. `MODEL_SCHEMA.md`: tabelas, colunas e relações. Nomes e descrições legíveis: é por eles que o Claude sabe onde buscar.
3. `dax_examples.md`: de 8 a 12 exemplos de DAX para as perguntas mais comuns, cada um rodado no modelo antes de entrar.
4. `__init__.py`: nome, assunto, fuso, moeda, regras fundamentais, exemplos de voz, sugestões e rótulos dos visuais.
5. Rode `ruff check .` e `pytest`, publique e troque `SEMANTIC_MODEL` e `POWERBI_DATASET_ID` no serviço `backend`.

Resposta errada no chat quase sempre se resolve no contexto: veja o DAX que o Claude escreveu (log do Railway ou `debug` no `/chat/v2`) e acrescente a regra ou o exemplo que faltou.

## Custos e limites

- Cada pergunta usa de 2 a 6 chamadas à API do Claude. A parte fixa (instruções e contexto) fica no cache de prompt.
- Rate limit por usuário: 20 pedidos por minuto e 300 por hora nos endpoints que custam API.
- A voz ao vivo cobra por minuto de áudio na OpenAI, mais as perguntas de dados no Claude.
- O Railway cobra pelo uso dos dois serviços e do Postgres.
