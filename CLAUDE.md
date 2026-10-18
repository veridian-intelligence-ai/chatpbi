# App Chat com os dados do Power BI

App que conversa com os dados de um modelo semântico do Power BI, com chat, voz ao vivo e visuais. API em Python e telas em React, sem nada de cliente. O nome nas telas e na conversa é ChatPBI: `frontend/src/config/app.ts`, `frontend/index.html`, `frontend/public/manifest.json` e a variável `ASSISTANT_NAME` do backend. O modelo ativo é escolhido pela variável `SEMANTIC_MODEL` do backend. Cada parte tem o próprio CLAUDE.md, que complementa este.

## As cinco partes, no caminho dos dados

1. Conexão com o Power BI: registro do app no Entra ID, service principal, grupo, permissão no workspace, Build no modelo e, em Direct Lake, a identidade fixa do modelo (identidade do workspace, sem SSO). Skill: `.claude/skills/conexao-power-bi`.
2. Backend no Railway (`backend/`): Python e FastAPI, dois serviços da mesma imagem. O serviço `backend` é a API: valida a sessão, chama o Claude, roda o DAX no modelo pela API Execute Queries, guarda as conversas no Postgres e abre a voz ao vivo da OpenAI. O serviço `auth` é o login pelo WorkOS. Skill: `.claude/skills/backend`.
3. Repositório no GitHub: este repositório. O original é um template público; a cópia de cada pessoa fica privada. Skill: `.claude/skills/repositorio`.
4. Frontend na Vercel (`frontend/`): Vite, React e TypeScript, com as telas de conversa, voz e visuais. Skill: `.claude/skills/frontend`.
5. Login com o WorkOS: e-mail e senha do WorkOS, e só entra quem está cadastrado no app (`auth.users`). Skill: `.claude/skills/login`.

Canal do WhatsApp, pela API oficial da Meta, para perguntar ao modelo por texto ou áudio e receber a resposta em texto ou em áudio. Skill: `.claude/skills/whatsapp`. Ele pode vir junto com o app web ou sozinho: no caminho só pelo WhatsApp, ficam de fora o login com o WorkOS e o frontend na Vercel (a skill `app-chat-power-bi-no-ar` conduz os dois caminhos).

Para montar ou mudar uma parte, siga a skill dela. Para montar o app inteiro numa conta nova, partindo só do modelo semântico e deste repositório, siga a skill `.claude/skills/app-chat-power-bi-no-ar`.

## Onde está cada coisa

| Caminho | O que tem |
|---|---|
| `backend/api/main.py` | A API: `/chat/v2`, `/chat/voice`, `/voice/*`, `/suggestions`, `/model`, conversas e `/whatsapp/webhook`. |
| `backend/api/orchestrator.py` | O ciclo Claude → `execute_dax` → Power BI → Claude. |
| `backend/api/prompts_fabric.py` | O prompt (com cache), a partir do pacote do modelo ativo. |
| `backend/api/whatsapp.py` | O canal do WhatsApp: assinatura do webhook, leitura das mensagens, envio, áudio e números autorizados. As rotas ficam em `main.py`. |
| `backend/api/realtime_voice.py` | A sessão da voz ao vivo (OpenAI Realtime) e a ferramenta `consultar_dados`. |
| `backend/api/semantic_models/<modelo>/` | O contexto de cada modelo: medidas, tabelas, regras, DAX validado, sugestões e rótulos. |
| `backend/auth_server.py` | O login (WorkOS) e as sessões. |
| `frontend/src/` | As telas. `components/chat/VoiceMode.tsx` e `lib/realtimeVoice.ts` são a voz. |
| `.claude/skills/` | Uma skill para cada parte, com o passo a passo, e a `app-chat-power-bi-no-ar`, do modelo semântico ao app no ar numa conta nova. |

## Regras

- Nenhum segredo entra no Git nem na conversa: o segredo do app no Entra ID, as chaves do Claude, da OpenAI e do WorkOS e a URL do banco. Os segredos ficam nas variáveis do Railway, e quem cola é a pessoa. Cada parte tem um `.env.example` só com os nomes.
- Todo número que o app mostra ou fala sai de uma consulta ao modelo. O Claude não estima nem inventa número, e o modelo de voz só repete o que a ferramenta `consultar_dados` devolveu.
- O contexto do modelo (`backend/api/semantic_models/<modelo>/`) muda junto com o modelo. Exemplo de DAX novo só entra depois de rodar no modelo (DAX query view do Power BI ou um notebook).
- Na comunicação, só "Power BI".
- Nada de cliente (nome, código, regra ou dado) entra neste repositório.
- Mudou uma rota, variável de ambiente ou fluxo: atualizar no mesmo commit o CLAUDE.md da parte, o `.env.example` e a skill.
- Antes de subir uma mudança: lint, tipos e testes da parte alterada (comandos no README). Os testes não chamam o Power BI, o Claude, a OpenAI nem o WorkOS de verdade.
- Português do Brasil em textos, documentação, commits e nomes do domínio. Termo técnico de ferramenta fica como a ferramenta chama.
