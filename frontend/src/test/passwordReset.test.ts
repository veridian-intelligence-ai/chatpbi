import { describe, it, expect } from 'vitest';
import { validateNewPassword, MIN_RESET_PASSWORD_LENGTH } from '@/lib/passwordReset';

describe('validateNewPassword', () => {
  it('accepts a 10+ character matching password', () => {
    expect(validateNewPassword({ next: 'abcdefghij', confirm: 'abcdefghij' })).toBeNull();
  });

  it('rejects a password shorter than 10 characters', () => {
    expect(validateNewPassword({ next: 'short1', confirm: 'short1' })).toBe('minLength');
  });

  it('rejects when the confirmation does not match', () => {
    expect(validateNewPassword({ next: 'abcdefghij', confirm: 'abcdefghik' })).toBe('mismatch');
  });

  it('checks length before the mismatch rule', () => {
    expect(validateNewPassword({ next: 'short', confirm: 'different' })).toBe('minLength');
  });

  it('pins the WorkOS minimum at 10', () => {
    expect(MIN_RESET_PASSWORD_LENGTH).toBe(10);
  });
});
