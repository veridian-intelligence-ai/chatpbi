/**
 * Endereços públicos dos dois serviços do backend: o login (`auth`) e a API.
 * Vêm de VITE_AUTH_BASE_URL e VITE_API_BASE_URL, que o build exige
 * (vite.config.ts). O código não tem endereço padrão: uma cópia do app nunca
 * fala, por engano, com o backend de outra instalação.
 */
function semBarraNoFim(url: string | undefined): string {
  return (url ?? '').trim().replace(/\/+$/, '');
}

export const AUTH_BASE_URL = semBarraNoFim(import.meta.env.VITE_AUTH_BASE_URL);

const KEYS = {
  token: 'veridian_token',
  apiUrl: 'veridian_api_url',
  companyName: 'veridian_company_name',
  userName: 'veridian_user_name',
  expiresAt: 'veridian_expires_at',
} as const;

export interface LoginResponse {
  token: string;
  api_url: string;
  company_name: string;
  user_name: string;
  expires_at?: string | number;
}

export interface Session {
  token: string;
  apiUrl: string;
  companyName: string;
  userName: string;
  expiresAt: number;
}

const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000;

function parseExpiresAt(value?: string | number): number {
  if (!value) return Date.now() + DEFAULT_TTL_MS;
  if (typeof value === 'number') {
    return value < 1e12 ? value * 1000 : value;
  }
  const asNum = Number(value);
  if (!isNaN(asNum)) return asNum < 1e12 ? asNum * 1000 : asNum;
  const parsed = Date.parse(value);
  return isNaN(parsed) ? Date.now() + DEFAULT_TTL_MS : parsed;
}

export function saveSession(data: LoginResponse): Session {
  const expiresAt = parseExpiresAt(data.expires_at);
  localStorage.setItem(KEYS.token, data.token);
  localStorage.setItem(KEYS.apiUrl, data.api_url);
  localStorage.setItem(KEYS.companyName, data.company_name ?? '');
  localStorage.setItem(KEYS.userName, data.user_name ?? '');
  localStorage.setItem(KEYS.expiresAt, String(expiresAt));
  return {
    token: data.token,
    apiUrl: data.api_url,
    companyName: data.company_name ?? '',
    userName: data.user_name ?? '',
    expiresAt,
  };
}

export function clearSession(): void {
  Object.values(KEYS).forEach((k) => localStorage.removeItem(k));
}

export function getSession(): Session | null {
  const token = localStorage.getItem(KEYS.token);
  const apiUrl = localStorage.getItem(KEYS.apiUrl);
  const expiresAtRaw = localStorage.getItem(KEYS.expiresAt);
  if (!token || !apiUrl || !expiresAtRaw) return null;
  return {
    token,
    apiUrl,
    companyName: localStorage.getItem(KEYS.companyName) ?? '',
    userName: localStorage.getItem(KEYS.userName) ?? '',
    expiresAt: Number(expiresAtRaw),
  };
}

export function isSessionValid(session: Session | null = getSession()): boolean {
  if (!session) return false;
  return session.expiresAt > Date.now();
}

export function getToken(): string | null {
  const s = getSession();
  return isSessionValid(s) ? s!.token : null;
}

/**
 * Endereço da API. Vale primeiro o do build (VITE_API_BASE_URL, obrigatório):
 * assim o app nunca segue um endereço errado que o login devolva. O `api_url`
 * do login fica só de reserva.
 */
export function getApiUrl(): string {
  const doBuild = semBarraNoFim(import.meta.env.VITE_API_BASE_URL);
  if (doBuild) return doBuild;
  const s = getSession();
  return isSessionValid(s) && s!.apiUrl ? s!.apiUrl : '';
}

/**
 * Exchanges a WorkOS (AuthKit) authorization code for a session: the single
 * sign-in path. Uses the `AUTH_ERROR:<status>` convention so callers can
 * distinguish 403 (user not provisioned), 401 (invalid/expired code) and 503.
 */
export async function workosCallbackRequest(code: string): Promise<LoginResponse> {
  const res = await fetch(`${AUTH_BASE_URL}/auth/workos/callback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) {
    throw new Error(`AUTH_ERROR:${res.status}`);
  }
  const data = (await res.json()) as LoginResponse;
  if (!data?.token || !data?.api_url) throw new Error('AUTH_INVALID_RESPONSE');
  return data;
}

/**
 * Headless password sign-in: the backend validates the credentials against
 * WorkOS and returns the same `LoginResponse` as any other session. Uses the
 * `AUTH_ERROR:<status>` convention so the UI can map 401 (bad credentials) and
 * 403 (user not provisioned) to specific messages.
 */
export async function passwordLoginRequest(email: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${AUTH_BASE_URL}/auth/workos/password-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw new Error(`AUTH_ERROR:${res.status}`);
  }
  const data = (await res.json()) as LoginResponse;
  if (!data?.token || !data?.api_url) throw new Error('AUTH_INVALID_RESPONSE');
  return data;
}

export async function logoutRequest(token: string): Promise<void> {
  try {
    await fetch(`${AUTH_BASE_URL}/auth/logout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
    });
  } catch {
    // best-effort
  }
}

/**
 * Starts the headless password-reset flow. The backend always responds 200
 * (neutral) to avoid account enumeration; we deliberately ignore the response
 * and let only transport failures surface, so the UI can show one fixed
 * message regardless of whether the email exists.
 */
export async function forgotPasswordRequest(email: string): Promise<void> {
  await fetch(`${AUTH_BASE_URL}/auth/workos/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
}

export type ResetPasswordResult = { ok: true } | { ok: false; status: number };

/**
 * Completes the headless password-reset flow with the token from the email
 * link. Returns a structured result: status 400 means the token is invalid or
 * expired; 429 (rate limit) and anything else map to a generic message.
 * `status: 0` signals a network/transport failure.
 */
export async function resetPasswordRequest(
  token: string,
  newPassword: string,
): Promise<ResetPasswordResult> {
  let res: Response;
  try {
    res = await fetch(`${AUTH_BASE_URL}/auth/workos/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  } catch {
    return { ok: false, status: 0 };
  }
  if (res.ok) return { ok: true };
  return { ok: false, status: res.status };
}
