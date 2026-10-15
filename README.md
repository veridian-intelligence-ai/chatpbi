# ChatPBI: chat com os dados do Power BI

App que conversa com os dados de um modelo semântico do Power BI, com chat, voz ao vivo e visuais (gráficos, cartões e tabelas). O Claude escreve as consultas DAX, o backend roda no modelo com o service principal do app e a tela mostra a resposta com o visual. O nome do app é ChatPBI: para trocar, veja `frontend/src/config/app.ts` e a variável `ASSISTANT_NAME` do backend.

O modelo ativo é escolhido no backend pela variável `SEMANTIC_MODEL`, e cada modelo tem um pacote em `backend/api/semantic_models/<modelo>/` com o contexto (medidas, tabelas, regras e exemplos de DAX validados).

## As cinco partes, no caminho dos dados

| Parte | Onde | O que faz | Skill |
|---|---|---|---|
| Conexão com o Power BI | Entra ID e workspace | O registro do app, o service principal, o grupo, a permissão no workspace e no modelo e a identidade fixa do modelo Direct Lake | `.claude/skills/conexao-power-bi` |
| Backend | Railway (`backend/`) | Dois serviços da mesma imagem: a API (chat, voz, sugestões, histórico) e o login; Postgres para sessões e conversas | `.claude/skills/backend` |
| Repositório | GitHub | O projeto, o contexto do modelo e as skills | `.claude/skills/repositorio` |
| Frontend | Vercel (`frontend/`) | As telas: conversa, voz ao vivo e visuais (Vite, React) | `.claude/skills/frontend` |
| Login | WorkOS | Quem pode entrar no app (e-mail e senha do WorkOS, usuário cadastrado no app) | `.claude/skills/login` |

Para montar o app inteiro numa conta nova, partindo só do modelo semântico e deste repositório, a skill `.claude/skills/app-chat-power-bi-no-ar` leva de ponta a ponta: as contas, os conectores no Claude, a cópia do repositório, as cinco partes e os testes.

## Voz ao vivo

Com `OPENAI_API_KEY` no serviço da API, o modo de voz usa a OpenAI Realtime por WebRTC. O backend entrega ao navegador só uma chave efêmera; quando o modelo de voz precisa de um número, ele chama a ferramenta `consultar_dados`, que passa a pergunta ao `/chat/voice` (Claude + DAX no Power BI). O número dito em voz sai sempre de uma consulta ao modelo.

## Rodar no computador

Precisa de Python 3.12 e Node.js 22.

```bash
# Backend: dois terminais, a partir de backend/
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # variáveis da API
cp .env.example auth.env        # variáveis do login
uvicorn auth_server:app --reload --port 8080
cd api && uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm ci
cp .env.example .env            # endereços do backend local
npm run dev
```

O frontend não tem endereço padrão do backend: `VITE_AUTH_BASE_URL` e `VITE_API_BASE_URL` são obrigatórios no build (no computador, o `frontend/.env`; na Vercel, as variáveis do projeto).

## Conferir

```bash
cd backend && ruff check . && pytest -q
cd frontend && npm run lint && npm run tipos && npm test && npm run build
```

Os testes não chamam o Power BI, o Claude, a OpenAI nem o WorkOS de verdade. O roteiro `backend/scripts/smoke_chat_v2.py` confere o app publicado com o token de uma sessão.

## Dados

O pacote `cota_parlamentar` usa os dados abertos da Câmara dos Deputados (https://dadosabertos.camara.leg.br), arquivos da cota parlamentar de 2023 em diante. Fornecedor pessoa física aparece só como "Pessoa física", sem nome nem CPF, e o nome de passageiro não é carregado.
