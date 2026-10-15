/**
 * Client-side validation for the headless password-reset screen.
 *
 * Returns an error code (mapped to an i18n key by the page) or `null` when the
 * input is valid. WorkOS enforces a 10-character minimum server-side; this is
 * the matching first-line UX check. Checks run in priority order.
 */
export const MIN_RESET_PASSWORD_LENGTH = 10;

export type ResetPasswordError = 'minLength' | 'mismatch';

export interface NewPasswordInput {
  next: string;
  confirm: string;
}

export function validateNewPassword({ next, confirm }: NewPasswordInput): ResetPasswordError | null {
  if (next.length < MIN_RESET_PASSWORD_LENGTH) return 'minLength';
  if (next !== confirm) return 'mismatch';
  return null;
}
