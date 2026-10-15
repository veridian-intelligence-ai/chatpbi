---
name: login
description: Configura o login do app com o WorkOS (projeto, ambiente, usuários com senha, URL de troca de senha) e o cadastro de quem pode entrar no app. Use quando for montar o login, liberar ou tirar alguém do app, mudar o domínio do app ou investigar erro de entrada.
---

# Login com o WorkOS

A tela do app manda e-mail e senha para o serviço `auth` do backend, que confere no WorkOS (`authenticate_with_password`) e devolve uma sessão do app. Só entra quem existe no WorkOS, com o e-mail verificado, e está cadastrado no app (`auth.users`).

## Passo a passo

1. **Projeto e ambiente** (conector do WorkOS). Projeto `app-chat-power-bi` com o ambiente de teste (Staging). Anote o Client ID.
2. **Variáveis do serviço `auth`** (skill `backend`): `WORKOS_CLIENT_ID` e, colada pela pessoa, `WORKOS_API_KEY`.
3. **Primeiro admin.** `SEED_ADMIN_EMAIL` (e `SEED_CLIENT_SLUG`, `SEED_CLIENT_NAME`, `SEED_ADMIN_NAME`) no serviço `auth`: o primeiro arranque cadastra essa pessoa no app.
4. **Usuário no WorkOS.** A pessoa precisa de conta com senha no ambiente (convite do WorkOS ou cadastro). Sem senha, ela usa "Esqueceu a senha?" na tela do app.
5. **Troca de senha.** No painel do WorkOS, Redirects, "Password reset URL": `https://<domínio do frontend>/reset-password`.

## Liberar mais alguém

1. A pessoa tem conta no WorkOS (convide pelo conector, `inviteUser`).
2. Cadastre no app: `POST /admin/users` no serviço `auth`, com o cabeçalho `X-Admin-Key` (exige `AUTH_SECRET_KEY` definida) ou um `INSERT` em `auth.users` com `role='member'` e `status='active'`.

## Conferir

1. Quem está cadastrado entra e usa o chat.
2. Quem tem conta no WorkOS, mas não está cadastrado, vê "Sua conta ainda não tem acesso à plataforma".
3. Sair volta para a tela de login.

## Tirar alguém do app

Mude o `status` da pessoa em `auth.users` para `inactive` (as sessões dela param de valer na hora) e, se quiser, remova a conta no WorkOS.
