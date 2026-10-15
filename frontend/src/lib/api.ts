import type { VeridianVisual } from '@/components/chat/visuals/types';
import { getApiUrl, getToken } from '@/lib/auth';

/**
 * fetch wrapper for the data API: injects the bearer token (without clobbering
 * a caller-provided Content-Type, so binary uploads like /stt keep theirs).
 */
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);
  return fetch(path, { ...init, headers });
}

export interface ChatV2Response {
  session_id: string;
  status: string;
  answer: string;
  analysis_type: string | null;
  analytics: Record<string, unknown> | null;
  plan: Record<string, unknown> | null;
  next_step_suggestions?: string[] | null;
  response_mode?: 'text' | 'visual' | null;
  visual?: VeridianVisual | null;
  error: string | null;
}

// /chat/v2 is slow by design: a multi-cut question runs 2-3 Anthropic turns
// (up to 180s each, server-side) plus ~10 Fabric queries, ~100s in production.
// The answer is persisted server-side before the response is sent, so aborting
// early only throws away work already paid for.
const CHAT_TIMEOUT_MS = 500_000;

export async function sendMessage(sessionId: string, message: string, module: string = 'fabric'): Promise<ChatV2Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

  try {
    const res = await apiFetch(`${getApiUrl()}/chat/v2`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message, module }),
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(`SERVER_ERROR:${res.status}`);
    }

    const data: ChatV2Response = await res.json();

    if (data.error && !data.answer) {
      throw new Error(data.error);
    }

    return data;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error('TIMEOUT');
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

export interface SuggestionsResponse {
  suggestions: string[];
}

export async function fetchSuggestions(
  sessionId: string,
  module: string,
  language: 'pt' | 'en',
): Promise<string[]> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await apiFetch(`${getApiUrl()}/suggestions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, module, language }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`SUGGESTIONS_ERROR:${res.status}`);
    const data: SuggestionsResponse = await res.json();
    if (!Array.isArray(data.suggestions)) throw new Error('SUGGESTIONS_INVALID');
    return data.suggestions;
  } finally {
    clearTimeout(timeoutId);
  }
}

export interface VoiceChatResponse {
  answer: string;
}

export async function sendVoiceMessage(
  sessionId: string,
  message: string,
  module: string = 'fabric',
): Promise<VoiceChatResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);
  try {
    const res = await apiFetch(`${getApiUrl()}/chat/voice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message, module }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`SERVER_ERROR:${res.status}`);
    const data = await res.json();
    if (!data || typeof data.answer !== 'string') throw new Error('VOICE_INVALID');
    return data as VoiceChatResponse;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw new Error('TIMEOUT');
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

export interface VoiceConfig {
  /** Voz ao vivo da OpenAI (Realtime, WebRTC). */
  realtime: boolean;
  /** Voz clássica: gravação + ElevenLabs STT/TTS. */
  classic: boolean;
}

export async function fetchVoiceConfig(): Promise<VoiceConfig> {
  const res = await apiFetch(`${getApiUrl()}/voice/config`);
  if (!res.ok) throw new Error(`VOICE_CONFIG_ERROR:${res.status}`);
  const data = await res.json();
  return { realtime: data?.realtime === true, classic: data?.classic === true };
}

export interface RealtimeSession {
  client_secret: string;
  expires_at: number | null;
  model: string;
}

/** Pede ao backend a chave efémera da sessão de voz ao vivo (a chave real fica no servidor). */
export async function createRealtimeSession(): Promise<RealtimeSession> {
  const res = await apiFetch(`${getApiUrl()}/voice/realtime/session`, { method: 'POST' });
  if (!res.ok) throw new Error(`REALTIME_SESSION_ERROR:${res.status}`);
  const data = await res.json();
  if (!data || typeof data.client_secret !== 'string' || !data.client_secret) {
    throw new Error('REALTIME_SESSION_INVALID');
  }
  return data as RealtimeSession;
}

export interface ModelInfo {
  /** Nome do modelo semântico do Power BI (ex.: "Cota parlamentar"). */
  name: string;
  description: string;
  subject: string;
  /** Código ISO da moeda dos valores (ex.: "BRL"). */
  currency: string;
  source: string;
}

export async function fetchModelInfo(): Promise<ModelInfo> {
  const res = await apiFetch(`${getApiUrl()}/model`);
  if (!res.ok) throw new Error(`MODEL_INFO_ERROR:${res.status}`);
  const data = await res.json();
  return {
    name: String(data?.name ?? ''),
    description: String(data?.description ?? ''),
    subject: String(data?.subject ?? ''),
    currency: String(data?.currency ?? 'BRL'),
    source: String(data?.source ?? 'Power BI'),
  };
}

export async function transcribeAudio(blob: Blob, mimeType: string): Promise<string> {
  const res = await apiFetch(`${getApiUrl()}/stt`, {
    method: 'POST',
    headers: { 'Content-Type': mimeType },
    body: blob,
  });
  if (!res.ok) throw new Error(`STT_ERROR:${res.status}`);
  const data = await res.json();
  if (!data || typeof data.text !== 'string') throw new Error('STT_INVALID');
  return data.text;
}

export async function fetchTTS(text: string): Promise<Blob> {
  const res = await apiFetch(`${getApiUrl()}/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`TTS_ERROR:${res.status}`);
  return res.blob();
}

export async function fetchConversations(): Promise<
  { session_id: string; title: string; updated_at: string; created_at: string }[]
> {
  const apiUrl = getApiUrl();
  const res = await apiFetch(`${apiUrl}/conversations`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.conversations || [];
}

export async function fetchConversationMessages(sessionId: string): Promise<
  { role: string; content: string; created_at: string; message_order: number }[]
> {
  const apiUrl = getApiUrl();
  const res = await apiFetch(`${apiUrl}/conversations/${sessionId}/messages`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.messages || [];
}

export async function deleteConversationApi(sessionId: string): Promise<void> {
  const apiUrl = getApiUrl();
  await apiFetch(`${apiUrl}/conversations/${sessionId}`, { method: 'DELETE' });
}

export async function renameConversationApi(
  sessionId: string,
  title: string
): Promise<void> {
  const apiUrl = getApiUrl();
  await apiFetch(`${apiUrl}/conversations/${sessionId}/title`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function resetChat(sessionId: string, module: string = 'fabric'): Promise<void> {
  const res = await apiFetch(`${getApiUrl()}/chat/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message: '', module }),
  });
  if (!res.ok) throw new Error(`RESET_ERROR:${res.status}`);
}
