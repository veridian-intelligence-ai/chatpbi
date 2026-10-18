---
name: app-chat-power-bi-no-ar
description: Use para colocar no ar, com as contas da pessoa, o app que conversa com os dados do Power BI, a partir do modelo semântico dela e do repositório do app.
---

# Colocar no ar o app que conversa com os dados do Power BI

O resultado é o app da pessoa no ar, com login, chat, voz e visuais, respondendo direto do modelo semântico dela, e, se ela quiser, também pelo WhatsApp, por texto ou áudio. Tudo fica nas contas dela: GitHub, Railway, Vercel, WorkOS, Claude e OpenAI.

A pessoa começa com duas coisas: o modelo semântico publicado no Power BI e o link do repositório template do app, que vai no e-mail de confirmação da compra e na área de membros: https://github.com/veridian-intelligence-ai/chatpbi. O resto nasce neste roteiro: as contas, os conectores no Claude, o repositório dela, a conexão com o Power BI, o contexto do modelo, o backend, o login, o frontend e os testes.

## Como conduzir

1. Crie uma lista de tarefas com as 9 etapas (e a 10, se a pessoa quiser o WhatsApp) e marque cada uma ao terminar. Uma etapa por vez, conferida antes da próxima:
   1. Modelo e acessos
   2. Contas e conectores
   3. Repositório da pessoa
   4. Conexão com o Power BI
   5. Contexto do modelo
   6. Backend no Railway
   7. Login com o WorkOS
   8. Frontend na Vercel
   9. Conferência de ponta a ponta
   10. WhatsApp (opcional)
   As etapas 4 e 5 não dependem uma da outra: se a TI demorar na 4, faça a 5 antes.
2. Fale em passos curtos e numerados, um por vez, dizendo o que a pessoa vai ver na tela. Na conversa, o nome é Power BI; as telas do Fabric (portal de administração, identidade do workspace) aparecem com o nome que têm.
3. A pessoa não programa: o Claude escreve e testa o código, abre os pull requests e explica o que muda. O Claude faz o que dá pelos conectores e pelo repositório. A pessoa faz o que pede login, cartão, papel de administrador ou segredo:
   - criar as contas e escolher os planos (o Claude não cria conta nem digita senha);
   - autorizar os conectores e os apps do GitHub;
   - as ações de administrador no Entra ID e no portal do Fabric, ou pedir à TI;
   - criar cada segredo e colar direto na variável do Railway;
   - dar o ok antes de cada publicação em produção: ligar um serviço ao repositório, merge na `main`, primeiro deploy na Vercel.
4. Segredo nunca passa pela conversa, pelo Git nem por arquivo: o segredo do app no Entra ID, as chaves do Claude, da OpenAI e do WorkOS e a URL do banco. Se um aparecer na conversa ou num commit, a pessoa troca na hora (apagar não basta).
5. Com um navegador ligado ao Claude, ele pode abrir as telas do Entra ID e do Power BI e preencher o que não é segredo; a pessoa confirma o que dá acesso. Se a mesma tela falhar duas vezes, passe os passos para a pessoa fazer.
6. Cada parte tem uma skill no repositório do app, em `.claude/skills/`: `conexao-power-bi`, `backend`, `login`, `frontend`, `repositorio` e `whatsapp`. Leia a da etapa antes de fazê-la: lá estão os detalhes e os erros de cada parte.

## Etapa 1. Modelo e acessos

Pergunte de uma vez, em lista curta:
1. O nome do workspace e do modelo semântico.
2. O modo do modelo: Import, DirectQuery ou Direct Lake. Se a pessoa não souber, a leitura do modelo (etapa 5) mostra.
3. Se o modelo tem RLS (segurança por linha).
4. Se a pessoa pode registrar apps e criar grupos no Entra ID, se é administradora do workspace e se é administradora do Fabric.
5. Se quer a voz ao vivo (pede uma chave da OpenAI).
6. Se quer perguntar também pelo WhatsApp, por texto ou áudio (pede um App da Meta, grátis no teste, e a mesma chave da OpenAI para o áudio).
7. De 10 a 20 perguntas que o time faz aos dados. Elas viram as sugestões, os exemplos de DAX e o teste final.

Pare e explique antes de seguir quando:
- o modelo estiver em "Meu workspace": o service principal precisa de papel num workspace compartilhado, e a pessoa move ou republica o modelo;
- o modelo tiver RLS: a API Execute Queries não aceita service principal com RLS, e o app não atende esse caso;
- faltar algum acesso de administrador: monte o pedido para a TI (fim desta skill) e siga com as etapas 2, 3 e 5 enquanto isso.

Direct Lake pede capacidade Fabric no workspace (vale o teste ou uma F2) e o passo da identidade fixa, na etapa 4.

## Etapa 2. Contas e conectores

1. A pessoa cria as contas que faltam: GitHub, Railway, Vercel, WorkOS, Claude Console (platform.claude.com, para a chave da API do Claude, com crédito) e OpenAI Platform (platform.openai.com, para a voz ao vivo e o áudio do WhatsApp). Para o WhatsApp, também uma conta pessoal no Facebook, que abre o portfólio empresarial e o App da Meta na etapa 10.
2. Os planos são escolha da pessoa, e cada serviço cobra pelo uso. O plano Hobby da Vercel é para uso pessoal; para a empresa, o Pro.
3. No Claude, em Configurações, Conectores, a pessoa liga e autoriza com a conta dela: GitHub, Railway, Vercel e WorkOS.
4. O Claude precisa ler o repositório do app e escrever no repositório da pessoa (branch e pull request). Esse acesso vem do GitHub ligado à sessão do Claude, com o app do GitHub instalado na conta da pessoa.
5. Confira cada conector com uma leitura: os workspaces no Railway, os times na Vercel, quem está conectado no WorkOS e os repositórios no GitHub. Se um falhar, a pessoa religa antes de seguir.

## Etapa 3. Repositório da pessoa

O repositório do app é um template público do Vinicius (https://github.com/veridian-intelligence-ai/chatpbi). A pessoa trabalha numa cópia dela, privada, de onde o Railway e a Vercel publicam. Para criar a cópia, a pessoa entra na conta dela do GitHub.

1. Criar a cópia:
   - repositório do app marcado como template: Use this template, Create a new repository, na conta da pessoa, Private, sem "Include all branches";
   - sem template: a pessoa cria um repositório privado e vazio (sem README, .gitignore ou licença), e o Claude clona o original e envia a `main` para ele.
   Fork não serve: o fork de um repositório público também fica público, e a cópia precisa ser privada, porque vai guardar o contexto do modelo da pessoa.
2. Em Settings, Actions, as Actions ficam ligadas: o CI roda ruff e pytest no backend e lint, tipos, testes e build no frontend.
3. Ajustar o CLAUDE.md da cópia, numa branch com pull request. A regra "Nada de cliente (nome, código, regra ou dado) entra neste repositório" é do repositório original. Na cópia, ela vira: "Nenhum dado exportado do modelo, segredo ou dado pessoal entra no repositório. O contexto do modelo (nomes, regras e DAX validado) entra."
4. Se os apps do Railway ou da Vercel no GitHub estiverem liberados só para repositórios escolhidos, a pessoa inclui o novo em GitHub, Settings, Applications, Configure.
5. Para receber as atualizações do app. A cópia feita pelo template começa com um commit só e não recebe merge do original, então a atualização traz só as mudanças desde a versão de que a pessoa partiu:
   1. remote `template` apontando para o repositório template e `git fetch template`;
   2. o commit de partida é o do template com a mesma árvore do primeiro commit da cópia (`git rev-parse <primeiro commit>^{tree}` comparado com `git log template/main --format='%H %T'`). Sem árvore igual, o último commit do template antes da data do primeiro commit da cópia;
   3. numa branch, `git cherry-pick <commit de partida>..template/main`. Conflito só aparece onde a pessoa mexeu no mesmo trecho: fica o que é dela (o pacote do modelo, o nome do app) e entra o que é do app;
   4. testes e pull request. O merge é da pessoa.
   Na cópia feita sem template (clone enviado para um repositório vazio), a história é a mesma do original: merge da `template/main` numa branch, testes e pull request.

## Etapa 4. Conexão com o Power BI

Detalhes e erros na skill `conexao-power-bi`. Em resumo:
1. Registrar o app no Entra ID: single tenant, sem redirect URI e sem permissões de API. Anotar o client ID e o tenant ID.
2. Grupo de segurança com o app como membro.
3. No portal de administração do Fabric, o administrador liga "Service principals can call Fabric public APIs" para o grupo e confere "Semantic Model Execute Queries REST API".
4. O grupo com o papel Viewer no workspace e o Build no modelo.
5. Direct Lake: identidade do workspace com o papel Viewer, e a fonte do modelo ligada a uma conexão de nuvem com essa identidade, sem SSO. Sem isso, toda consulta do app volta com 401 `PowerBINotAuthorizedException`.
6. Anotar o id do workspace e o do modelo, que estão no endereço do modelo no navegador.
7. O segredo do app só é criado na etapa 6, na hora de colar no Railway.

## Etapa 5. Contexto do modelo

O app acerta quando conhece o modelo. O contexto fica num pacote em `backend/api/semantic_models/<pacote>/`, com nome curto em snake_case (`vendas_empresa`, por exemplo), feito a partir do modelo da pessoa. O modelo não muda: nome técnico ganha o nome que o time usa no glossário e no MODEL_SCHEMA.md. Renomear no modelo é escolha da pessoa.

### Ler o modelo

Use a primeira opção que a pessoa conseguir:
1. Workspace com capacidade Fabric: o Claude escreve um notebook Python com o semantic link (`sempy.fabric`: `list_tables`, `list_columns`, `list_measures` e `list_relationships`) que grava num JSON as tabelas, as colunas, as medidas com o DAX e as descrições, e as relações. A pessoa importa o notebook no workspace, roda e manda o JSON.
2. Power BI Desktop, na exibição de consulta DAX: `EVALUATE INFO.VIEW.TABLES()`, `EVALUATE INFO.VIEW.COLUMNS()`, `EVALUATE INFO.VIEW.MEASURES()` e `EVALUATE INFO.VIEW.RELATIONSHIPS()`. A pessoa copia cada resultado e cola na conversa.
3. Projeto do Power BI: a pessoa salva o relatório como projeto (PBIP) e anexa a pasta do modelo (`<nome>.SemanticModel`), com os arquivos TMDL.

Depois, uma segunda rodada no mesmo lugar, com consultas que o Claude escreve:
- os valores de cada coluna de texto que serve de filtro (até 50 por coluna);
- o primeiro e o último dia com dados;
- as medidas principais por ano, para ter a ordem de grandeza.

Na conversa entram só nomes e resultados agregados, nunca as linhas dos fatos. Coluna com dado pessoal (nome de pessoa física, e-mail, CPF, telefone) entra só com a contagem de valores.

### Escrever o pacote

Copie o pacote `cota_parlamentar` e troque o conteúdo:
1. `MODEL_SCHEMA.md`: cada tabela com o que é uma linha dela, as colunas com o que são (as ocultas marcadas) e as relações.
2. `SEMANTIC_MODEL.md`: o que são os dados (origem, período, moeda e modo do modelo), cada medida com o que é e os cuidados, o glossário (termo do time → tabela, coluna ou medida), as regras que mudam a resposta e as perguntas-tipo.
3. `__init__.py`, com as mesmas constantes do pacote original:
   - `MODEL_NAME` (o nome exato do modelo no Power BI), `MODEL_DESCRIPTION`, `DATA_SUBJECT`, `TIMEZONE`, `DEFAULT_LANGUAGE`, `CURRENCY_LABEL` e `CURRENCY_CODE`;
   - `FUNDAMENTAL_RULES`: de 2 a 4 regras com o título "REGRA FUNDAMENTAL", como qual data usar, o que fica de fora por padrão e o período incompleto;
   - `VOICE_EXAMPLES`: duas respostas curtas, só de estilo;
   - `SUGGESTION_TEMPLATES`: de 12 a 17 perguntas, tiradas das perguntas do time;
   - `build_context_dax` e `build_context`: um placeholder dinâmico, sem dado pessoal (o produto ou a região que mais vendeu no ano anterior, por exemplo). Sem linhas, `build_context` devolve só `ano_corrente` e `ano_anterior`;
   - `DIMENSION_LABELS` e `MONEY_LIKE_KEYS`.
4. `dax_examples.md`: de 8 a 12 exemplos para as perguntas mais comuns, cada um com a pergunta, o DAX, a resposta-modelo e o `visual_hint` quando a resposta for série ou ranking.

O DAX dos exemplos segue o pacote original: começa com EVALUATE (ou DEFINE); agrupa com SUMMARIZECOLUMNS e filtra com TREATAS; valor único com ROW e CALCULATE; ranking com TOPN e ORDER BY; coluna calculada com nome curto e diferente do nome da medida; tabela com espaço ou acento entre aspas simples; ano corrente incompleto comparado só com os mesmos meses do ano anterior.

### Validar e subir

1. Todo exemplo roda no modelo antes de entrar: no notebook (`evaluate_dax`) ou na exibição de consulta DAX. Exemplo com erro é corrigido e roda de novo, ou sai.
2. As respostas-modelo usam os números da validação, com a data de referência no começo do arquivo. Se a empresa não quiser números dela no repositório, a resposta-modelo fica só com o formato, e o começo do arquivo diz isso.
3. Inclua o pacote em `PACOTES` (`backend/api/tests/test_semantic_model_packages.py`), com uma linha de exemplo no formato que `build_context` lê. Suba o `PROMPT_VERSION` em `backend/api/prompts_fabric.py`; se um teste conferir o valor, ajuste junto.
4. Em `backend/`: `ruff check .` e `pytest`. Com tudo verde, pull request. O merge na `main` é da pessoa.

## Etapa 6. Backend no Railway

Detalhes na skill `backend`. Pelo conector do Railway:
1. Projeto novo com o template `postgres`.
2. Serviço `backend` (API): repositório da pessoa, branch `main`, diretório raiz `/backend`, healthcheck `/health` e domínio público.
3. Serviço `auth` (login): mesmo repositório e diretório, start command `sh -c 'cd /app && uvicorn auth_server:app --host 0.0.0.0 --port ${PORT:-8080}'`, `PORT=8080`, healthcheck `/health` e domínio público na porta 8080.
4. As variáveis entram antes de ligar o repositório, porque o primeiro deploy já precisa delas:
   - nos dois serviços: `DATABASE_URL=${{Postgres.DATABASE_URL}}` (com o nome do serviço do banco) e `ALLOWED_ORIGINS` (`http://localhost:8080` por enquanto; o domínio da Vercel entra na etapa 8);
   - na API: `POWERBI_TENANT_ID`, `POWERBI_CLIENT_ID`, `POWERBI_WORKSPACE_ID` e `POWERBI_DATASET_ID`; as referências `FABRIC_TENANT_ID=${{POWERBI_TENANT_ID}}`, `FABRIC_CLIENT_ID=${{POWERBI_CLIENT_ID}}`, `FABRIC_CLIENT_SECRET=${{POWERBI_CLIENT_SECRET}}`, `FABRIC_WORKSPACE_ID=${{POWERBI_WORKSPACE_ID}}` e `FABRIC_DEFAULT_DATASET_ID=${{POWERBI_DATASET_ID}}`; `SEMANTIC_MODEL=<pacote>`; `ANTHROPIC_MODEL` e `ANTHROPIC_VOICE_MODEL`, com os valores do `backend/.env.example`;
   - no login: `WORKOS_CLIENT_ID` (etapa 7), `API_PUBLIC_URL` (o domínio público da API; opcional, porque o frontend usa o `VITE_API_BASE_URL`) e o primeiro admin: `SEED_CLIENT_SLUG`, `SEED_CLIENT_NAME`, `SEED_ADMIN_EMAIL` (o e-mail da pessoa) e `SEED_ADMIN_NAME`.
5. Os segredos, que a pessoa cria e cola em Variables do serviço:
   - na API: `POWERBI_CLIENT_SECRET` (Entra ID, Certificates & secrets, New client secret, validade de 180 dias: anotar a data para trocar antes), `ANTHROPIC_API_KEY` e, para a voz ao vivo, `OPENAI_API_KEY`;
   - no login: `WORKOS_API_KEY`.
6. Ligar cada serviço ao repositório publica em produção: peça o ok. Se a ferramenta recusar, a pessoa liga no painel, em Settings, Source, Connect Repo.
7. Confira pelo conector: deploy com sucesso, `/health` respondendo nos dois domínios e os logs sem erro. O primeiro arranque cria os esquemas `auth` e `ai` e o admin das `SEED_*`.

## Etapa 7. Login com o WorkOS

Detalhes na skill `login`:
1. No WorkOS, o ambiente Staging para começar. Em Authentication, "Email + Password" ligado. O Client ID vai para `WORKOS_CLIENT_ID` no serviço `auth`.
2. A pessoa cria a API key no painel do WorkOS e cola em `WORKOS_API_KEY` no Railway.
3. Em Redirects, "Password reset URL": `https://<domínio do frontend>/reset-password` (o domínio sai na etapa 8).
4. A pessoa precisa de usuário no WorkOS com o mesmo e-mail de `SEED_ADMIN_EMAIL`, com senha e e-mail verificado: pelo convite do WorkOS (manda e-mail, então confirme antes) ou por "Esqueceu a senha?" na tela do app.

## Etapa 8. Frontend na Vercel

Detalhes na skill `frontend`:
1. Projeto ligado ao repositório da pessoa, diretório raiz `frontend` (o `vercel.json` já define o build).
2. Variáveis obrigatórias, para Production e Preview, sem barra no fim: `VITE_AUTH_BASE_URL` (domínio do serviço `auth`) e `VITE_API_BASE_URL` (domínio da API). O código não tem endereço padrão e o build falha sem elas. Elas entram no build: mudou, publique de novo.
3. O primeiro deploy publica em produção: com o ok da pessoa. Confira o build.
4. De volta ao Railway: o domínio da Vercel (`https://<projeto>.vercel.app`, sem barra) em `ALLOWED_ORIGINS` dos dois serviços. E a URL de troca de senha no WorkOS (etapa 7, passo 3).
5. Opcional: o nome do app, que vem como ChatPBI. Ele fica em `frontend/src/config/app.ts`, no título e nas metas de `frontend/index.html`, em `frontend/public/manifest.json` e na variável `ASSISTANT_NAME` do serviço `backend`, que é o nome com que o assistente se apresenta no chat e na voz. A logo fica em `frontend/src/components/brand/Logo.tsx` e os ícones em `frontend/public/`. Por pull request.

## Etapa 9. Conferência de ponta a ponta

1. A pessoa entra com o e-mail do admin.
2. As sugestões iniciais aparecem, sem aviso de contexto.
3. Cinco perguntas do time no chat, com pelo menos um visual. O DAX de cada pergunta fica nos logs do serviço `backend`, entre `[DAX_QUERY]` e `[/DAX_QUERY]`, e o Claude lê pelo conector.
4. Teste de acerto: três números do app comparados com o relatório do Power BI que o time já usa, com o mesmo filtro. Diferença é contexto faltando: corrija o glossário, a regra ou o exemplo, rode o exemplo no modelo, abra pull request e confira de novo depois do merge.
5. Voz ao vivo, só em HTTPS: o navegador pede o microfone, uma pergunta de dados volta falada e aparece escrita na conversa.
6. Para liberar o time: conta no WorkOS e cadastro no app, para cada pessoa (skill `login`).

| O que aparece | Causa provável |
|---|---|
| Erro de CORS no navegador | Domínio do frontend fora de `ALLOWED_ORIGINS`, ou com barra no fim |
| O build da Vercel para em "Faltam VITE_AUTH_BASE_URL" | As variáveis da etapa 8, passo 2, não estão na Vercel |
| "Sua conta ainda não tem acesso à plataforma" | A pessoa está no WorkOS, mas não em `auth.users` |
| `workos_email_not_verified` | E-mail não verificado no WorkOS: confirme pelo convite, ou marque como verificado no WorkOS, com o ok da pessoa |
| Aviso de contexto nas sugestões | A consulta ao modelo falhou: o motivo está no aviso e no log do `backend` |
| `AADSTS7000215` | Segredo do Entra ID errado ou vencido |
| 404 `PowerBIEntityNotFound` | Grupo fora do workspace, app fora do grupo ou configuração do locatário desligada. Logo depois de criar o grupo, espere alguns minutos |
| 401 `PowerBINotAuthorizedException` | Direct Lake sem a identidade fixa (etapa 4, passo 5) |
| Número errado na resposta | Contexto: falta regra, termo no glossário ou exemplo |
| A voz não abre | Falta `OPENAI_API_KEY`, o endereço não é HTTPS ou o microfone foi negado |

## Etapa 10. WhatsApp (opcional)

Só se a pessoa disse sim na etapa 1, item 6, e com a etapa 9 conferida. Siga a skill `whatsapp`, do passo 1 ao 9 do teste, com o número de teste da Meta, sem custo:
1. A pessoa cria o portfólio empresarial e o App da Meta com o WhatsApp, e cadastra o próprio celular como destinatário de teste.
2. O Claude define no Railway o identificador do número, o texto de verificação e a lista de números; a pessoa cola o token e a chave secreta do App.
3. A pessoa configura o webhook na Meta com o endereço da API, assina o campo `messages` e liga o App à conta do WhatsApp (`subscribed_apps`).
4. Conferência: uma pergunta em texto, uma de seguimento em áudio, que volta como mensagem de voz, e "novo".
5. Antes de usar no dia a dia, o token permanente do usuário do sistema (skill `whatsapp`, "Token permanente"): o temporário vence em 24 horas.

Quem entra pelo WhatsApp vê o modelo inteiro, como no app. Libere só quem já tem usuário no app.

## Depois do ar

- O segredo do Entra ID vence em 180 dias: a pessoa cria outro antes e cola no Railway.
- WhatsApp: o token temporário vence em 24 horas; o permanente não vence. Cada resposta em áudio cobra a voz da OpenAI pelo uso.
- Custos: cada pergunta usa de 2 a 6 chamadas à API do Claude; a voz ao vivo cobra por minuto na OpenAI; Railway, Vercel e WorkOS cobram pelo plano e pelo uso.
- Mudou o modelo (medida ou tabela nova): atualize o pacote, rode os exemplos no modelo e suba o `PROMPT_VERSION`.
- Atualização do app original: etapa 3, passo 5.

## Pedido para a TI

Sem os acessos de administrador, use o modelo de pedido da skill `conexao-power-bi` e pare a etapa 4 até a TI responder. O segredo do app nunca vai por e-mail: quem cria cola direto no Railway.
