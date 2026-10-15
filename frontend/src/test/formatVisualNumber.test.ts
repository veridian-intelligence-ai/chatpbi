import { describe, it, expect } from 'vitest';
import { formatVisualNumber } from '@/components/chat/visuals/format';

describe('formatVisualNumber', () => {
  it('renders integers without decimals (counts)', () => {
    expect(formatVisualNumber(10834)).toBe('10.834');
  });

  it('keeps two decimals for fractional values', () => {
    expect(formatVisualNumber(6.63)).toBe('6,63');
  });

  it('pads a single decimal place to two', () => {
    expect(formatVisualNumber(6.6)).toBe('6,60');
  });

  it('rounds to two decimals', () => {
    expect(formatVisualNumber(6.637)).toBe('6,64');
  });

  it('groups thousands in pt-BR', () => {
    expect(formatVisualNumber(1234567)).toBe('1.234.567');
  });

  it('treats integer-valued floats as integers', () => {
    expect(formatVisualNumber(50.0)).toBe('50');
  });

  it('passes strings through unchanged (pre-formatted backend values)', () => {
    expect(formatVisualNumber('N/A')).toBe('N/A');
    expect(formatVisualNumber('12/05/2026')).toBe('12/05/2026');
  });

  it('returns the string form of non-finite numbers without crashing', () => {
    expect(formatVisualNumber(NaN)).toBe('NaN');
    expect(formatVisualNumber(Infinity)).toBe('Infinity');
  });
});
