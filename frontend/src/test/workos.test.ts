import { describe, it, expect, beforeEach } from 'vitest';
import {
  generateState,
  storeState,
  readAndClearState,
  buildWorkosLoginUrl,
  parseCallbackParams,
  validateState,
  classifyWorkosError,
} from '@/lib/workos';
import { AUTH_BASE_URL } from '@/lib/auth';

describe('generateState', () => {
  it('returns a 32-char lowercase hex string', () => {
    expect(generateState()).toMatch(/^[0-9a-f]{32}$/);
  });

  it('produces a different value on each call', () => {
    expect(generateState()).not.toBe(generateState());
  });
});

describe('storeState / readAndClearState', () => {
  beforeEach(() => sessionStorage.clear());

  it('round-trips the stored state', () => {
    storeState('abc123');
    expect(readAndClearState()).toBe('abc123');
  });

  it('clears the state after reading (single-use)', () => {
    storeState('abc123');
    readAndClearState();
    expect(readAndClearState()).toBeNull();
  });

  it('returns null when nothing was stored', () => {
    expect(readAndClearState()).toBeNull();
  });
});

describe('buildWorkosLoginUrl', () => {
  it('points at the backend login endpoint with an encoded state', () => {
    expect(buildWorkosLoginUrl('a b/c')).toBe(
      `${AUTH_BASE_URL}/auth/workos/login?state=a%20b%2Fc`,
    );
  });
});

describe('parseCallbackParams', () => {
  it('extracts code and state from a full query string', () => {
    expect(parseCallbackParams('?code=abc&state=xyz')).toEqual({ code: 'abc', state: 'xyz' });
  });

  it('works without the leading question mark', () => {
    expect(parseCallbackParams('code=abc&state=xyz')).toEqual({ code: 'abc', state: 'xyz' });
  });

  it('returns null for a missing code', () => {
    expect(parseCallbackParams('?state=xyz')).toEqual({ code: null, state: 'xyz' });
  });

  it('returns null for a missing state', () => {
    expect(parseCallbackParams('?code=abc')).toEqual({ code: 'abc', state: null });
  });

  it('returns nulls for an empty query string', () => {
    expect(parseCallbackParams('')).toEqual({ code: null, state: null });
  });

  it('decodes url-encoded values', () => {
    expect(parseCallbackParams('?code=a%2Bb&state=x%20y')).toEqual({ code: 'a+b', state: 'x y' });
  });
});

describe('validateState', () => {
  it('passes when both values are present and equal', () => {
    expect(validateState('match', 'match')).toBe(true);
  });

  it('fails on a mismatch', () => {
    expect(validateState('one', 'two')).toBe(false);
  });

  it('fails when the received state is missing', () => {
    expect(validateState(null, 'stored')).toBe(false);
  });

  it('fails when the stored state is missing', () => {
    expect(validateState('received', null)).toBe(false);
  });

  it('fails when both are empty strings', () => {
    expect(validateState('', '')).toBe(false);
  });
});

describe('classifyWorkosError', () => {
  it('maps 403 to "notProvisioned"', () => {
    expect(classifyWorkosError('AUTH_ERROR:403')).toBe('notProvisioned');
  });

  it('maps 401 to "expired"', () => {
    expect(classifyWorkosError('AUTH_ERROR:401')).toBe('expired');
  });

  it('maps 503 to "generic"', () => {
    expect(classifyWorkosError('AUTH_ERROR:503')).toBe('generic');
  });

  it('maps an unknown/network error to "generic"', () => {
    expect(classifyWorkosError('Failed to fetch')).toBe('generic');
  });
});
