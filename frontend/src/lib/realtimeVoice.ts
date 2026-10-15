/**
 * Voz ao vivo com a OpenAI Realtime API, por WebRTC.
 *
 * O backend entrega só uma chave efémera (POST /voice/realtime/session) com a
 * sessão já configurada: modelo, voz, instruções e a ferramenta
 * `consultar_dados`. O browser liga-se à OpenAI com essa chave, manda o áudio
 * do microfone e toca o áudio do modelo.
 *
 * Os números nunca saem do modelo de voz: quando ele chama `consultar_dados`,
 * a pergunta vai ao /chat/voice (Claude + DAX no Power BI) e a resposta volta
 * como resultado da ferramenta, que o modelo lê em voz alta.
 */

export const REALTIME_CALLS_URL = 'https://api.openai.com/v1/realtime/calls';
export const REALTIME_TOOL_NAME = 'consultar_dados';

export type RealtimeVoiceState = 'connecting' | 'listening' | 'thinking' | 'speaking' | 'closed';

export interface RealtimeServerEvent {
  type: string;
  [key: string]: unknown;
}

export type RealtimeClientEvent = Record<string, unknown>;

export interface RealtimeHandlers {
  onState: (state: RealtimeVoiceState) => void;
  /** Consulta os dados e devolve a resposta em texto (ou null se falhar). */
  onToolCall: (question: string) => Promise<string | null>;
  onUserTranscript?: (text: string) => void;
  onAssistantTranscript?: (text: string) => void;
  onError?: (message: string) => void;
}

interface RouterHandlers extends RealtimeHandlers {
  send: (event: RealtimeClientEvent) => void;
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

/** Lê a pergunta dos argumentos (JSON) da chamada à ferramenta. */
export function parseToolQuestion(rawArguments: unknown): string {
  const raw = asString(rawArguments);
  if (!raw) return '';
  try {
    const parsed = JSON.parse(raw) as { pergunta?: unknown };
    return asString(parsed?.pergunta).trim();
  } catch {
    return '';
  }
}

/**
 * Trata os eventos do servidor (data channel "oai-events"). Fica separado do
 * WebRTC para ser testável sem browser.
 *
 * Regra do protocolo: não se pede uma resposta nova (`response.create`)
 * enquanto outra está em curso; se o resultado da ferramenta chegar antes do
 * `response.done`, o pedido fica guardado e sai no `response.done`.
 */
export class RealtimeEventRouter {
  private responseActive = false;
  private pendingResponseCreate = false;
  private pendingCalls = 0;
  private readonly handledCalls = new Set<string>();

  constructor(private readonly handlers: RouterHandlers) {}

  async handle(event: RealtimeServerEvent): Promise<void> {
    switch (event.type) {
      case 'session.created':
        this.handlers.onState('listening');
        return;
      case 'input_audio_buffer.speech_started':
        if (this.pendingCalls === 0) this.handlers.onState('listening');
        return;
      case 'response.created':
        this.responseActive = true;
        return;
      case 'response.done':
        this.responseActive = false;
        await this.handleCallsInResponse(event);
        if (this.pendingResponseCreate) {
          this.pendingResponseCreate = false;
          this.handlers.send({ type: 'response.create' });
        }
        return;
      case 'output_audio_buffer.started':
        this.handlers.onState('speaking');
        return;
      case 'output_audio_buffer.stopped':
      case 'output_audio_buffer.cleared':
        if (this.pendingCalls === 0) this.handlers.onState('listening');
        return;
      case 'response.function_call_arguments.done':
        await this.handleFunctionCall(
          asString(event.call_id),
          asString(event.name) || REALTIME_TOOL_NAME,
          event.arguments,
        );
        return;
      case 'conversation.item.input_audio_transcription.completed': {
        const text = asString(event.transcript).trim();
        if (text) this.handlers.onUserTranscript?.(text);
        return;
      }
      case 'response.output_audio_transcript.done':
      case 'response.audio_transcript.done': {
        const text = asString(event.transcript).trim();
        if (text) this.handlers.onAssistantTranscript?.(text);
        return;
      }
      case 'error': {
        const error = event.error as { message?: unknown } | undefined;
        this.handlers.onError?.(asString(error?.message) || 'erro da sessão de voz');
        return;
      }
      default:
        return;
    }
  }

  /** Chamadas que só aparecem no `response.done` (rede: evento perdido). */
  private async handleCallsInResponse(event: RealtimeServerEvent): Promise<void> {
    const response = event.response as { output?: unknown } | undefined;
    const output = Array.isArray(response?.output) ? response.output : [];
    for (const item of output) {
      const call = item as { type?: unknown; call_id?: unknown; name?: unknown; arguments?: unknown };
      if (call?.type !== 'function_call') continue;
      const callId = asString(call.call_id);
      if (!callId || this.handledCalls.has(callId)) continue;
      void this.handleFunctionCall(callId, asString(call.name) || REALTIME_TOOL_NAME, call.arguments);
    }
  }

  private async handleFunctionCall(callId: string, name: string, rawArguments: unknown): Promise<void> {
    if (!callId || this.handledCalls.has(callId)) return;
    this.handledCalls.add(callId);

    if (name !== REALTIME_TOOL_NAME) {
      this.sendToolOutput(callId, { erro: `Ferramenta desconhecida: ${name}.` });
      return;
    }
    const question = parseToolQuestion(rawArguments);
    if (!question) {
      this.sendToolOutput(callId, { erro: 'A pergunta chegou vazia. Peça para a pessoa repetir.' });
      return;
    }

    this.pendingCalls += 1;
    this.handlers.onState('thinking');
    let answer: string | null = null;
    try {
      answer = await this.handlers.onToolCall(question);
    } catch {
      answer = null;
    } finally {
      this.pendingCalls -= 1;
    }
    this.sendToolOutput(
      callId,
      answer
        ? { resposta: answer }
        : { erro: 'Não foi possível consultar os dados agora.' },
    );
  }

  private sendToolOutput(callId: string, output: Record<string, string>): void {
    this.handlers.send({
      type: 'conversation.item.create',
      item: { type: 'function_call_output', call_id: callId, output: JSON.stringify(output) },
    });
    if (this.responseActive) {
      this.pendingResponseCreate = true;
    } else {
      this.handlers.send({ type: 'response.create' });
    }
  }
}

export interface RealtimeConnection {
  close: () => void;
  /** Microfone em uso (para o nível de áudio da animação). */
  micStream: MediaStream;
}

export interface StartRealtimeOptions {
  clientSecret: string;
  audioElement: HTMLAudioElement;
  handlers: RealtimeHandlers;
  /** Frase pedida ao modelo logo que a ligação abre (opcional). */
  greeting?: string;
  callsUrl?: string;
  fetchImpl?: typeof fetch;
}

export function realtimeSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.RTCPeerConnection !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

/** Abre a sessão de voz ao vivo. Levanta erro se a ligação falhar. */
export async function startRealtimeVoice(options: StartRealtimeOptions): Promise<RealtimeConnection> {
  const { audioElement, handlers } = options;
  const pc = new RTCPeerConnection();
  let dataChannel: RTCDataChannel | null = null;
  let micStream: MediaStream | null = null;
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    try {
      dataChannel?.close();
    } catch {
      /* noop */
    }
    pc.getSenders().forEach((sender) => {
      try {
        sender.track?.stop();
      } catch {
        /* noop */
      }
    });
    try {
      pc.close();
    } catch {
      /* noop */
    }
    micStream?.getTracks().forEach((track) => track.stop());
    try {
      audioElement.pause();
    } catch {
      /* noop */
    }
    audioElement.srcObject = null;
    handlers.onState('closed');
  };

  try {
    handlers.onState('connecting');

    pc.ontrack = (event) => {
      audioElement.srcObject = event.streams[0];
      audioElement.play().catch(() => {
        /* autoplay bloqueado: o próximo toque do utilizador desbloqueia */
      });
    };

    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const stream = micStream;
    stream.getAudioTracks().forEach((track) => pc.addTrack(track, stream));

    dataChannel = pc.createDataChannel('oai-events');
    const channel = dataChannel;
    const router = new RealtimeEventRouter({
      ...handlers,
      send: (event) => {
        if (channel.readyState === 'open') channel.send(JSON.stringify(event));
      },
    });
    channel.onmessage = (message) => {
      let event: RealtimeServerEvent;
      try {
        event = JSON.parse(String(message.data)) as RealtimeServerEvent;
      } catch {
        return;
      }
      void router.handle(event);
    };
    channel.onopen = () => {
      if (options.greeting) {
        channel.send(
          JSON.stringify({ type: 'response.create', response: { instructions: options.greeting } }),
        );
      }
    };

    pc.onconnectionstatechange = () => {
      if (!closed && (pc.connectionState === 'failed' || pc.connectionState === 'closed')) {
        handlers.onError?.('a ligação de voz caiu');
        close();
      }
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const doFetch = options.fetchImpl ?? fetch;
    const response = await doFetch(options.callsUrl ?? REALTIME_CALLS_URL, {
      method: 'POST',
      body: offer.sdp,
      headers: {
        Authorization: `Bearer ${options.clientSecret}`,
        'Content-Type': 'application/sdp',
      },
    });
    if (!response.ok) throw new Error(`REALTIME_SDP_ERROR:${response.status}`);
    const answerSdp = await response.text();
    await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });

    return { close, micStream: stream };
  } catch (error) {
    close();
    throw error;
  }
}
