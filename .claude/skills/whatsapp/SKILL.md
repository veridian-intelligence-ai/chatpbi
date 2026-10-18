---
name: whatsapp
description: Liga o canal do WhatsApp do app (WhatsApp Cloud API, oficial da Meta) para a pessoa perguntar ao modelo semântico pelo WhatsApp, por texto ou áudio, e receber a resposta em texto ou em áudio. Cobre o App da Meta, o número, o token, o webhook no Railway, a voz da resposta e a lista de números autorizados. Use quando for ligar o WhatsApp, liberar ou tirar um número, trocar o token, mudar a voz ou investigar por que o WhatsApp não responde.
---

# Canal do WhatsApp

A pessoa manda a pergunta no WhatsApp, por texto ou áudio. A Meta entrega a mensagem no webhook da API (`/whatsapp/webhook`, serviço `backend` no Railway), o orquestrador consulta o modelo do Power BI e a resposta volta pela Graph API. Pergunta em texto recebe texto; pergunta em áudio recebe uma mensagem de voz. Código em `backend/api/whatsapp.py` e no fim de `backend/api/main.py`.

## Como a resposta é montada

- Uma conversa por número (`wa-<número>`), guardada no Postgres como as do app. O Claude recebe as últimas 12 mensagens, então pergunta de seguimento ("e no ano passado?", "quanto disso é de X?") usa o contexto da anterior. A mensagem "novo" começa uma conversa nova.
- Texto e áudio usam o mesmo modelo do Claude (`WHATSAPP_MODEL`). No áudio, entra também o bloco de voz, que só muda o formato: frases curtas, sem marcação.
- As instruções do canal pedem que toda observação saia dos números consultados (variação, peso no total, ranking, o que puxou) e proíbem frase óbvia ou condicional ("se voltar a investir, a receita pode subir"), causa sem dado e conselho genérico.
- Áudio recebido: transcrito pela OpenAI (`OPENAI_TRANSCRIBE_MODEL`). Resposta em áudio: gerada pela OpenAI (`gpt-4o-mini-tts`) ou pela ElevenLabs, convertida para OGG/Opus com o `ffmpeg` da imagem e enviada como mensagem de voz. Se a voz falhar, a resposta vai em texto.

## Regras

- Só a API oficial da Meta (Cloud API). Biblioteca não oficial (Baileys, Evolution API e parecidas) vai contra os termos do WhatsApp e pode banir o número.
- Só respondem os números de `WHATSAPP_ALLOWED_NUMBERS`, cada um ligado ao e-mail de um usuário ativo do app (`auth.users`). Número fora da lista é ignorado, sem resposta.
- O service principal consulta o modelo inteiro. Com o canal ligado, todo número da lista vê todos os dados do modelo. Para modelo com RLS, este canal ainda não serve: a API Execute Queries não aceita service principal em modelo com RLS.
- O assistente responde só sobre os dados do modelo. A política da Meta proíbe assistente de IA de uso geral no WhatsApp Business desde 15/01/2026.
- Os segredos (`WHATSAPP_TOKEN`, `WHATSAPP_APP_SECRET`) ficam nas variáveis do Railway, e quem cola é a pessoa. A IA nunca pede o token na conversa.
- Aceitar termos da Meta e mudar configuração da conta do Business é decisão da pessoa: a IA mostra onde clicar e espera.

## Variáveis do serviço `backend`

| Variável | O que é | Segredo |
|---|---|---|
| `WHATSAPP_TOKEN` | Token de acesso do WhatsApp (temporário de 24 horas no teste, permanente do usuário do sistema depois). | Sim |
| `WHATSAPP_APP_SECRET` | Chave secreta do App da Meta (Configurações do app > Básico). Confere a assinatura de cada webhook. | Sim |
| `WHATSAPP_PHONE_NUMBER_ID` | Identificação do número de telefone (WhatsApp > Configuração da API). | Não |
| `WHATSAPP_VERIFY_TOKEN` | Texto que a IA gera, igual no Railway e na tela do webhook da Meta. | Não |
| `WHATSAPP_ALLOWED_NUMBERS` | `numero=email`, separados por vírgula. Número com código do país, só dígitos: `5511912345678=ana@empresa.com`. | Não |
| `WHATSAPP_MODEL` | Opcional. Modelo do Claude do canal, para texto e áudio (padrão: `ANTHROPIC_MODEL`). | Não |
| `WHATSAPP_TTS_PROVIDER` | Opcional. Voz da resposta em áudio: `openai` (padrão) ou `elevenlabs`. | Não |
| `WHATSAPP_TTS_VOICE` | Opcional. Na OpenAI, o nome da voz (padrão `coral`); na ElevenLabs, o Voice ID (padrão: `ELEVENLABS_VOICE_ID`). | Não |
| `WHATSAPP_TTS_MODEL` | Opcional. Na OpenAI, padrão `gpt-4o-mini-tts`; na ElevenLabs, padrão `eleven_v4`, com queda para `eleven_multilingual_v2`. | Não |
| `WHATSAPP_GRAPH_VERSION` | Opcional. Versão da Graph API (padrão `v25.0`). | Não |

Sem as quatro primeiras, o canal fica desligado e `/whatsapp/webhook` responde 404. O áudio usa a `OPENAI_API_KEY` que a voz ao vivo já usa; sem ela, o canal responde só a texto. Com `WHATSAPP_TTS_PROVIDER=elevenlabs`, a resposta em áudio usa a `ELEVENLABS_API_KEY`.

## Passo a passo do teste (número de teste da Meta, sem custo)

Antes de começar: o backend está no ar, com os dois serviços no Railway, e a pessoa tem um usuário ativo em `auth.users` (o admin das `SEED_*`). O login e o frontend só são precisos para o app web: no caminho só pelo WhatsApp (skill `app-chat-power-bi-no-ar`), eles ficam de fora. Da Meta, parta do pressuposto de que ela não tem nada além de uma conta pessoal no Facebook: sem conta de desenvolvedor, sem portfólio empresarial, sem App e sem número. Cada passo diz quem faz.

0. **Voz da resposta (pergunte antes).** OpenAI, que já está no app e não pede conta nova, ou ElevenLabs, com vozes mais naturais, que pede uma conta em elevenlabs.io e um plano escolhido pela pessoa. Com ElevenLabs: a pessoa cria a conta, gera a API key e cola em `ELEVENLABS_API_KEY` no Railway, escolhe a voz na Voice Library e passa o Voice ID; o Claude define `WHATSAPP_TTS_PROVIDER=elevenlabs` e `WHATSAPP_TTS_VOICE`.
1. **Conta de desenvolvedor e portfólio (pessoa).** Em developers.facebook.com, "Começar", entrar com o Facebook e confirmar o telefone e o e-mail que a Meta pedir: isso cria a conta de desenvolvedor. Depois, em business.facebook.com, "Criar portfólio", com o nome da empresa e o e-mail de trabalho. Se a pessoa já tiver um portfólio, usa o dela.
2. **App da Meta (pessoa, com a IA guiando).** Em developers.facebook.com > Meus apps > Criar app (o nome não pode ter "WhatsApp" nem outra marca da Meta: a Meta recusa), escolher o caso de uso "Conectar-se com clientes pelo WhatsApp" (ou o tipo Empresa) e ligar ao portfólio do passo 1. A Meta cria uma conta do WhatsApp Business de teste e um número de teste. Aceitar os termos é decisão da pessoa. O número de teste é do portfólio, não do app: um segundo app no mesmo portfólio recebe o mesmo número, e os dois apps respondem à mesma conversa. Para dois apps com números separados, cada um no seu portfólio.
3. **Destinatário de teste (pessoa).** Em WhatsApp > Configuração da API, no campo "Para", clicar em "Gerenciar lista de números" e adicionar o celular da pessoa. A Meta manda um código pelo WhatsApp para confirmar. O número de teste só manda mensagem para até 5 números dessa lista.
4. **Anotar (pessoa passa à IA).** Na mesma tela: o "Identificador do número de telefone" (vai em `WHATSAPP_PHONE_NUMBER_ID`) e o "Identificador da conta do WhatsApp Business" (WABA, usado no passo 8). Os dois não são segredo.
5. **Variáveis no Railway.** A IA define `WHATSAPP_PHONE_NUMBER_ID`, gera e define `WHATSAPP_VERIFY_TOKEN` (texto aleatório, mostrado à pessoa) e define `WHATSAPP_ALLOWED_NUMBERS` com o celular da pessoa e o e-mail dela no app. A pessoa cola, no serviço `backend`:
   - `WHATSAPP_TOKEN`: o token temporário da tela Configuração da API (botão "Gerar token de acesso").
   - `WHATSAPP_APP_SECRET`: Configurações do app > Básico > Chave secreta do app > Mostrar.
   Depois de salvar, o Railway reinicia o serviço. A IA confere nos logs que subiu.
   Primeira mensagem: o celular da pessoa só reconhece o número de teste depois que ele manda a primeira mensagem (antes, o WhatsApp oferece "convidar"). Em Configuração da API, a pessoa clica em "Gerar token" e em "Enviar mensagem", com o celular dela como destinatário, e responde essa conversa.
6. **Webhook (pessoa, com a IA guiando).** Em WhatsApp > Configuração > Webhook > Editar: URL de callback `https://<domínio da API>/whatsapp/webhook` e, em "Verificar token", o mesmo `WHATSAPP_VERIFY_TOKEN`. Clicar em "Verificar e salvar". A IA confere nos logs a linha `GET /whatsapp/webhook ... 200`.
7. **Campo `messages` (pessoa).** Ainda em Webhook > Campos do webhook, assinar `messages`. Na tela nova da Meta, isso acontece sozinho depois de "Verificar e salvar" (avisos "Automatically subscribed to messages").
8. **Ligar o App à conta do WhatsApp (pessoa).** Sem este passo, a Meta verifica o webhook e assina os campos, mas não entrega as mensagens, mesmo com o campo `messages` assinado. No Explorador da Graph API (developers.facebook.com/tools/explorer), escolher o App, colar o token do passo 5, método `POST` e o caminho `<WABA>/subscribed_apps`, com o WABA do passo 4. Clicar em "Enviar". A resposta esperada é `{"success": true}`.
9. **Conferir (pessoa manda, IA lê os logs).**
   - "oi" do celular cadastrado: chega a resposta, e o log mostra `[whatsapp] resposta em texto enviada`.
   - Uma pergunta de dados em texto e, depois, uma de seguimento em áudio ("e no ano passado?"): chega uma mensagem de voz que usa o contexto da anterior, e o log mostra `[whatsapp] resposta em áudio enviada (openai/gpt-4o-mini-tts)`.
   - "novo": começa uma conversa nova.

## Token permanente (antes de usar de verdade)

O token temporário vale 24 horas. Depois disso, a Meta recusa o envio (log `envio falhou: status=401` com o código 190) e o WhatsApp para de responder.

1. Em business.facebook.com > Configurações > Usuários > Usuários do sistema, criar um usuário do sistema Administrador (ou usar um que já exista).
2. Nos três pontinhos do usuário, "Atribuir ativos": o App da Meta, com controle total, e, em "Contas do WhatsApp", a conta do passo 4, com controle total.
3. "Gerar token": escolher o App, validade "Nunca" e as permissões `whatsapp_business_messaging` e `whatsapp_business_management`.
4. A pessoa cola o token novo em `WHATSAPP_TOKEN` no Railway. Não clicar em "Revogar tokens": derruba os tokens que outras integrações usam.

## Mais pessoas e número próprio

- **Liberar alguém:** no teste, a pessoa adiciona o número na lista de destinatários da Meta (passo 3). Em qualquer caso, a IA acrescenta `numero=email` em `WHATSAPP_ALLOWED_NUMBERS`, e o e-mail precisa ser de um usuário ativo do app: no caminho com o app web, pela skill `login`; no caminho só pelo WhatsApp, a IA acrescenta o e-mail em `SEED_MEMBER_EMAILS`, no serviço `auth`, e o reinício do serviço cadastra a pessoa. Lembrar a pessoa de que quem entra vê o modelo inteiro.
- **Número próprio** (mais de 5 pessoas ou uso no dia a dia): um número que não esteja em nenhum WhatsApp, verificado na conta do WhatsApp Business, com o nome de exibição aprovado pela Meta e uma forma de pagamento na conta. Segundo a tabela de preços da Meta, mensagem que não é template, enviada dentro da janela de 24 horas depois da mensagem da pessoa, não é cobrada, e é assim que este canal responde. Conferir a tabela atual antes de passar preço ao cliente.

## Mudar a voz da resposta

- **OpenAI (padrão):** `WHATSAPP_TTS_VOICE` com o nome de uma voz da OpenAI (por exemplo `coral`, `nova`, `sage` ou `ash`). Sem conta nova: usa a `OPENAI_API_KEY`.
- **ElevenLabs:** `WHATSAPP_TTS_PROVIDER=elevenlabs`, a pessoa cola a `ELEVENLABS_API_KEY` e escolhe a voz na Voice Library (o Voice ID vai em `WHATSAPP_TTS_VOICE`). O modelo padrão é o `eleven_v4`; se ele falhar, o app tenta o `eleven_multilingual_v2`.

## Quando não responde

- `/whatsapp/webhook` dá 404: falta uma das quatro variáveis obrigatórias.
- Webhook não verifica na Meta: o `WHATSAPP_VERIFY_TOKEN` difere entre o Railway e a Meta, ou a URL não é a da API.
- Webhook verificado, mas nenhuma linha `POST /whatsapp/webhook` nos logs quando a pessoa manda mensagem: falta o campo `messages` (passo 7) ou o `subscribed_apps` (passo 8).
- Log `assinatura inválida` (401): `WHATSAPP_APP_SECRET` não é a chave secreta deste App.
- Log `número fora da lista`: o número não está em `WHATSAPP_ALLOWED_NUMBERS`, ou está sem o código do país.
- Log `número sem usuário ativo`: o e-mail da lista não existe em `auth.users` ou está inativo.
- Log `envio falhou` com status 401 e código 190: o token expirou. Gerar o permanente.
- Log `envio falhou` com o código 131030: o número de destino não está na lista de destinatários de teste da Meta.
- Log `resposta em áudio falhou, vai em texto`: a voz falhou (chave, crédito ou voz inexistente); a pessoa recebe em texto. O motivo vem na mesma linha.
- O WhatsApp mostra o áudio como arquivo de música, e não como mensagem de voz: a imagem está sem o `ffmpeg` (Dockerfile).
