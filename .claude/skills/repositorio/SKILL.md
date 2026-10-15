---
name: repositorio
description: Cria e organiza o repositório do app no GitHub (privado, com backend, frontend, contexto do modelo, skills e CI), dá acesso ao Railway e à Vercel e define o que nunca entra no Git. Use quando for criar o repositório, copiar o app para outra conta, configurar o CI ou conferir se há segredo no código.
---

# Repositório no GitHub

O repositório guarda o projeto inteiro: o código das duas partes que são publicadas, o contexto do modelo e as skills. O passo a passo de cada parte fica na skill dela.

## Estrutura

```
app-chat-power-bi/
  CLAUDE.md                 instruções do projeto para o Claude Code
  README.md
  .claude/skills/           app-chat-power-bi-no-ar (do zero ao ar) e uma por parte: conexao-power-bi, backend, repositorio, frontend, login
  .github/workflows/ci.yml  lint, testes e build das duas partes
  backend/                  API e login (Railway, Python), com o contexto de cada modelo em api/semantic_models/
  frontend/                 telas (Vercel, Vite e React)
```

## Passo a passo

Quem recebeu o app como template cria a cópia com Use this template (skill `app-chat-power-bi-no-ar`, etapa 3) e começa no passo 3.

1. **Criar o repositório** no GitHub, privado e vazio (sem README, .gitignore ou licença, que já vêm no projeto).
2. **Enviar o projeto** para a branch `main`.
3. **Dar acesso ao Railway e à Vercel.** Os dois publicam a partir do repositório pelos apps deles no GitHub. Se o app do Railway ou da Vercel estiver instalado só para repositórios escolhidos, inclua este em GitHub, Settings, Applications, Configure.
4. **CI.** O workflow `.github/workflows/ci.yml` roda `ruff` e `pytest` no backend e lint, tipos, testes e build no frontend, em todo push e pull request.
5. **Trabalho do dia a dia.** Mudança nova numa branch, com pull request. O Railway e a Vercel publicam a `main`.

## O que nunca entra no Git

- O segredo do app no Entra ID, as chaves das APIs do Claude e da OpenAI, a API key do WorkOS e a URL do banco.
- Arquivos `.env` (o `.gitignore` já bloqueia). Cada parte tem um `.env.example` só com os nomes.
- Dados da empresa. O app lê os dados do modelo na hora; o repositório guarda só o contexto (nomes e regras).

Antes de cada commit, confira: `git diff --cached` sem chave, token ou senha. Se um segredo entrar num commit, troque o segredo na hora (apagar o commit não basta).
