---
name: conexao-power-bi
description: Liga o app ao modelo semântico do Power BI com um service principal do Entra ID (registro do app, segredo, grupo, configurações do locatário, permissão no workspace, Build no modelo e identidade fixa do modelo Direct Lake) e confere a conexão. Use quando for montar a conexão com o Power BI, trocar o segredo do app, ligar outro modelo ou quando o backend responder sem acesso ao Power BI.
---

# Conexão com o Power BI

O backend consulta o modelo pela API Execute Queries do Power BI com a identidade de um app registrado no Entra ID (o service principal). O acesso aos dados vem do papel do grupo no workspace, não de permissões de API no registro do app.

## Antes de começar

- O modelo semântico já está publicado num workspace. Um modelo em Direct Lake precisa de capacidade Fabric (vale o teste do Fabric ou uma F2).
- Quem segue esta skill precisa poder registrar apps e criar grupos no Entra ID, e ser administrador do workspace. As configurações do locatário pedem o administrador do Fabric.
- Se a pessoa não tiver esses acessos, monte o pedido para a TI (modelo no fim desta skill) e pare até a TI responder.

## O que o app não precisa

- Papel de Admin, Member ou Contributor no workspace: Viewer e Build bastam.
- Permissões de API no registro do app, como Tenant.Read.All. Elas servem para as APIs de administrador, e a Microsoft pede que um app com service principal não tenha permissões de admin do Power BI.

## Passo a passo

1. **Registrar o app.** No Entra admin center (entra.microsoft.com), em App registrations, New registration: nome `app-chat-power-bi`, "Single tenant only", sem redirect URI. Anote o Application (client) ID e o Directory (tenant) ID. O service principal é criado junto (aparece em Enterprise apps).
2. **Não adicionar permissões de API.** O registro não precisa de permissões do Power BI nem de consentimento do administrador: quem dá o acesso é o grupo no workspace.
3. **Criar o grupo.** Em Groups, New group: tipo Security, nome `Power BI - Service principals`, membro: o app `app-chat-power-bi`.
4. **Conferir as configurações do locatário.** No portal de administração do Fabric (Admin portal, Tenant settings):
   - "Service principals can call Fabric public APIs" ligada, para a organização inteira ou para o grupo do passo 3.
   - "Semantic Model Execute Queries REST API" ligada.
   Mudar essas configurações é decisão do administrador do Fabric. A IA confere e mostra onde ficam, mas não liga sozinha.
5. **Dar acesso no workspace.** No workspace do modelo, Manage access, Add people or groups: o grupo, com o papel Viewer.
6. **Dar Build no modelo.** No modelo semântico, Manage permissions, Direct access, no menu do grupo: Add build. A API Execute Queries exige Read e Build.
7. **Ligar a identidade fixa no modelo (Direct Lake).** Um modelo em Direct Lake lê o lakehouse com SSO, ou seja, com o login de quem pergunta. A API Execute Queries não aceita service principal nesse modo, e a consulta volta com 401 `PowerBINotAuthorizedException`. A correção é o modelo ler o lakehouse sempre com a identidade do workspace:
   1. Nas configurações do workspace (Workspace settings), aba Workspace identity: + Workspace identity. A identidade leva o nome do workspace e nasce sem papel nele.
   2. Em Manage access, Add people or groups: a identidade do workspace, com o papel Viewer. Dar acesso é com a pessoa: a IA deixa a tela pronta e a pessoa confirma.
   3. Nas configurações do modelo, em Gateway and cloud connections, no campo "Maps to": Create a connection. Preencha o nome da conexão, escolha "Workspace identity" em Authentication method e deixe desmarcado "Use SSO via Azure AD for DirectQuery queries". Clique em Create.
   4. De volta em "Maps to", escolha a conexão nova e clique em Apply.
   Modelo em Import não precisa deste passo.
8. **Anotar os ids.** O id do workspace e o do modelo estão no endereço do modelo no Fabric: `.../groups/<workspace>/...` e `.../datasets/<modelo>` ou `.../modeling/<modelo>/...`.
9. **Criar o segredo, na hora de usar.** No registro do app, Certificates & secrets, New client secret (validade de 180 dias). O valor aparece uma vez só: a pessoa copia e cola direto na variável `POWERBI_CLIENT_SECRET` do backend, no Railway. O segredo nunca vai para a conversa, para o Git nem para um arquivo. Anote a data de vencimento para trocar antes.
10. **Variáveis do backend.** `POWERBI_TENANT_ID`, `POWERBI_CLIENT_ID`, `POWERBI_WORKSPACE_ID` e `POWERBI_DATASET_ID` (ids, sem segredo) e `POWERBI_CLIENT_SECRET` (colado pela pessoa), no serviço `backend` do Railway. O código lê `FABRIC_*`, que apontam para essas (skill `backend`).

## Conferir

Com o app no ar, entre e abra uma conversa nova: as sugestões iniciais saem de uma consulta ao modelo, e `POST /suggestions` volta sem `context_warning` quando a conexão está boa (com erro, o motivo aparece nesse campo e no log do serviço `backend`). No computador, `python scripts/validate_fabric_auth.py`, a partir de `backend/` e com as variáveis no `.env`, testa o token e uma consulta. Os erros mais comuns:

| Resposta | Causa provável |
|---|---|
| `AADSTS7000215` ou `AADSTS7000222` | Segredo errado ou vencido: crie outro e cole no Railway |
| `AADSTS700016` | Client ID ou tenant errado |
| 404 `Workspace ... cannot be found` ou `PowerBIEntityNotFound` | O grupo não está no workspace, o app não está no grupo, ou a configuração "Service principals can call Fabric public APIs" está desligada para ele. No primeiro uso do segredo, o Power BI pode levar alguns minutos para reconhecer o grupo |
| 401 `PowerBINotAuthorizedException` | Modelo Direct Lake em SSO: ligue a identidade fixa (passo 7). Em modelo Import, confira o Build (passo 6) e as configurações do locatário |
| Erro de permissão na consulta | Falta o Build no modelo (passo 6) ou o papel Viewer da identidade do workspace (passo 7) |

## Limites da API Execute Queries

- Modelo com RLS não aceita service principal.
- Modelo com SSO não aceita service principal. Em Direct Lake, use a identidade fixa (passo 7).
- Até 100 mil linhas ou 1 milhão de valores por consulta e 120 consultas por minuto por usuário.

## Modelo de pedido para a TI

> Preciso conectar um app interno ao modelo semântico "<nome>" do Power BI, no workspace "<nome>", só para leitura. Peço:
> 1. Registrar um app no Entra ID (single tenant, sem redirect URI e sem permissões de API) e me passar o client ID e o tenant ID.
> 2. Criar o grupo de segurança "Power BI - Service principals", com esse app como membro.
> 3. Ligar no portal do Fabric "Service principals can call Fabric public APIs" para esse grupo e conferir "Semantic Model Execute Queries REST API".
> 4. Dar ao grupo o papel Viewer no workspace e a permissão Build no modelo.
> 5. Se o modelo for Direct Lake: criar a identidade do workspace, dar a ela o papel Viewer e ligar o modelo a uma conexão com essa identidade, sem SSO.
> 6. Criar um segredo do app e colar direto na variável do servidor, sem me enviar por e-mail.
