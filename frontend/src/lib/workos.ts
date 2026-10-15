/**
 * Client-side helpers for the WorkOS (AuthKit) sign-in flow.
 *
 * Kept free of React and i18n so the security-sensitive pieces — the anti-CSRF
 * state and the callback parsing — can be unit-tested directly. The actual
 * token exchange lives in `auth.ts` (`workosCallbackRequest`) and reuses the
 * same `LoginResponse` contract as the password login.
 */
import { AUTH_BASE_URL } from './auth';

/** sessionStorage key holding the anti-CSRF state across the AuthKit round-trip. */
const STATE_STORAGE_KEY = 'veridian_workos_state';

/** Error categories surfaced by the /callback page, mapped to i18n keys there. */
export type WorkosCallbackError = 'notProvisioned' | 'expired' | 'state' | 'generic';

/** Generates a random, opaque state token (32 hex chars) for CSRF protection. */
export function generateState(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Persists the state for the duration of the AuthKit redirect (same tab). */
export function storeState(state: string): void {
  sessionStorage.setItem(STATE_STORAGE_KEY, state);
}

/**
 * Reads the stored state and removes it in the same step: the value is
 * single-use, so a replayed callback cannot pass validation a second time.
 */
export function readAndClearState(): string | null {
  const state = sessionStorage.getItem(STATE_STORAGE_KEY);
  sessionStorage.removeItem(STATE_STORAGE_KEY);
  return state;
}

/** Builds the backend entry point that 302-redirects to the AuthKit page. */
export function buildWorkosLoginUrl(state: string): string {
  return `${AUTH_BASE_URL}/auth/workos/login?state=${encodeURIComponent(state)}`;
}

/** Extracts `code` and `state` from a callback URL query string. */
export function parseCallbackParams(search: string): {
  code: string | null;
  state: string | null;
} {
  const params = new URLSearchParams(search);
  return { code: params.get('code'), state: params.get('state') };
}

/**
 * Anti-CSRF check: the state returned by AuthKit must be present and exactly
 * match the one we stored before the redirect. Missing values never pass.
 */
export function validateState(received: string | null, stored: string | null): boolean {
  return !!received && !!stored && received === stored;
}

/**
 * Maps an `AUTH_ERROR:<status>` message from the token exchange to a UI error
 * category. 403 is exclusively "user not provisioned" on this endpoint; 401 is
 * an invalid/expired code; everything else (incl. 503 and network) is generic.
 */
export function classifyWorkosError(message: string): WorkosCallbackError {
  if (message.includes('AUTH_ERROR:403')) return 'notProvisioned';
  if (message.includes('AUTH_ERROR:401')) return 'expired';
  return 'generic';
}
