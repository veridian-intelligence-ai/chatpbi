import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { LanguageProvider } from '@/i18n/LanguageContext';
import { useChat } from '@/hooks/useChat';
import * as api from '@/lib/api';

vi.mock('@/lib/session', () => ({
  getSessionId: () => 'test-session',
  resetSessionId: () => 'new-session',
}));

vi.mock('@/lib/api', () => ({
  sendMessage: vi.fn(),
  resetChat: vi.fn().mockResolvedValue(undefined),
  sendVoiceMessage: vi.fn(),
  fetchConversations: vi.fn().mockResolvedValue([]),
  fetchConversationMessages: vi.fn().mockResolvedValue([]),
  deleteConversationApi: vi.fn().mockResolvedValue(undefined),
  renameConversationApi: vi.fn().mockResolvedValue(undefined),
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <LanguageProvider>{children}</LanguageProvider>
);

const okResponse = (answer: string) => ({
  session_id: 'test-session',
  status: 'ok',
  answer,
  analysis_type: null,
  analytics: null,
  plan: null,
  error: null,
});

describe('useChat — retry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchConversations).mockResolvedValue([]);
  });

  it('resends the last question on retry without duplicating the user bubble', async () => {
    vi.mocked(api.sendMessage)
      .mockRejectedValueOnce(new Error('Failed to fetch'))
      .mockResolvedValueOnce(okResponse('Sales were 42k.'));

    const { result } = renderHook(() => useChat(), { wrapper });

    // First attempt fails (network).
    await act(async () => {
      await result.current.send('What were sales last month?');
    });

    expect(result.current.error).toBe('Failed to fetch');
    expect(result.current.messages.filter((m) => m.role === 'user')).toHaveLength(1);
    expect(result.current.messages.filter((m) => m.role === 'assistant')).toHaveLength(0);

    // Retry succeeds.
    await act(async () => {
      await result.current.retry();
    });

    expect(result.current.error).toBeNull();
    // Still exactly one user bubble — retry must not re-append the question.
    expect(result.current.messages.filter((m) => m.role === 'user')).toHaveLength(1);
    const assistant = result.current.messages.filter((m) => m.role === 'assistant');
    expect(assistant).toHaveLength(1);
    expect(assistant[0].content).toBe('Sales were 42k.');

    expect(vi.mocked(api.sendMessage)).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.sendMessage)).toHaveBeenLastCalledWith(
      'test-session',
      'What were sales last month?',
      'fabric',
    );
  });

  it('does nothing when there is no user question to retry', async () => {
    const { result } = renderHook(() => useChat(), { wrapper });

    await act(async () => {
      await result.current.retry();
    });

    expect(vi.mocked(api.sendMessage)).not.toHaveBeenCalled();
    expect(result.current.messages).toHaveLength(0);
  });
});
