---
name: frontend
description: Publica o frontend do app na Vercel (Vite e React, pasta frontend) e confere as telas de login, conversa, visuais e voz ao vivo. Use quando for publicar o frontend, mudar o endereço do backend, ajustar uma tela ou investigar a voz ou um gráfico.
---

# Frontend na Vercel

O frontend fica em `frontend/`: as telas de login, conversa, visuais e voz. Fala direto com os dois serviços do backend (login e API), com o token da sessão.

## Antes de começar

- O backend está no ar, com os endereços públicos da API e do login (skill `backend`).

## Passo a passo (pelo conector da Vercel)

1. **Projeto.** Projeto `app-chat-power-bi` ligado ao repositório, com o diretório raiz `frontend`. O `frontend/vercel.json` já define o framework (Vite), o build (`npm run build`), a pasta `dist` e o redirecionamento das rotas para o `index.html`.
2. **Endereços do backend (obrigatórios).** Nas variáveis da Vercel, para Production e Preview: `VITE_AUTH_BASE_URL` (serviço `auth`) e `VITE_API_BASE_URL` (serviço `backend`), sem barra no fim. O código não tem endereço padrão e o build falha sem elas, para uma cópia do app nunca falar com o backend de outra instalação. Mudou um endereço, publique de novo: as variáveis entram no build. O app usa sempre o `VITE_API_BASE_URL`; o endereço que o login devolve fica só de reserva.
3. **CORS.** O domínio do frontend precisa estar em `ALLOWED_ORIGINS` dos dois serviços do backend.
4. **Publicar** a `main` e conferir o build.

O frontend não tem segredo: as chaves ficam no backend.

## Conferir

1. A página de login abre; e-mail e senha do WorkOS entram no app.
2. Conversa: as sugestões iniciais aparecem e uma pergunta volta com a resposta e, quando cabe, o visual.
3. Voz ao vivo: o navegador pede o microfone, o modelo cumprimenta, uma pergunta sobre os dados volta falada e aparece escrita na conversa. Só em HTTPS.

## A voz

Com a voz ao vivo ligada no backend (`OPENAI_API_KEY`), o navegador fala direto com a OpenAI por WebRTC, com uma chave efêmera pedida ao backend. O número falado vem da ferramenta `consultar_dados`, que chama o `/chat/voice`. Sem a voz ao vivo, o app usa a voz clássica (gravação + ElevenLabs no backend).
