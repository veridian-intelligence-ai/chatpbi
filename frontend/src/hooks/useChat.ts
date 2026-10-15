import { useState, useCallback, useRef, useEffect } from 'react';
import { getSessionId, resetSessionId } from '@/lib/session';
import {
  sendMessage,
  resetChat,
  sendVoiceMessage,
  fetchConversations,
  fetchConversationMessages,
  deleteConversationApi,
  renameConversationApi,
} from '@/lib/api';
import { parseAssistantContent } from '@/lib/messageContent';
import type { VeridianVisual } from '@/components/chat/visuals/types';
import { useLanguage } from '@/i18n/LanguageContext';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  analysisType?: string | null;
  analytics?: Record<string, unknown> | null;
  nextStepSuggestions?: string[];
  visual?: VeridianVisual | null;
  isNew?: boolean;
}

export interface Conversation {
  session_id: string;
  title: string;
  updated_at: string;
  created_at?: string;
}

export function useChat() {
  const { t } = useLanguage();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string>(() => getSessionId());
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  // Bumped on a fresh send (send / sendVoice) so the view pins the new question
  // to the top; bumped separately on history load so the view jumps to the bottom.
  const [lastSendNonce, setLastSendNonce] = useState(0);
  const [historyLoadNonce, setHistoryLoadNonce] = useState(0);

  const sessionIdRef = useRef(sessionId);

  const refreshConversations = useCallback(async () => {
    const list = await fetchConversations();
    setConversations(list);
    return list;
  }, []);

  useEffect(() => {
    refreshConversations();
  }, [refreshConversations]);

  const translateError = useCallback((msg: string): string => {
    if (msg.startsWith('SERVER_ERROR:')) return `${t('error.serverCommunication')} (${msg.split(':')[1]})`;
    if (msg === 'TIMEOUT') return t('error.timeout');
    if (msg.startsWith('RESET_ERROR:')) return `${t('error.resetConversation')} (${msg.split(':')[1]})`;
    return msg;
  }, [t]);

  // Runs the assistant round-trip for an already-known question. Shared by
  // `send` (first attempt) and `retry` (re-attempt) so retrying never appends a
  // duplicate user bubble — the failed question is already in `messages`.
  const runQuery = useCallback(async (text: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const data = await sendMessage(sessionIdRef.current, text, 'fabric');

      const parsed = parseAssistantContent(data.answer);
      const aiMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: parsed.answer || data.answer,
        timestamp: new Date(),
        analysisType: data.analysis_type,
        analytics: data.analytics,
        nextStepSuggestions: data.next_step_suggestions ?? parsed.nextStepSuggestions,
        visual: data.visual ?? parsed.visual ?? null,
        isNew: true,
      };
      setMessages(prev => [...prev, aiMsg]);
      setActiveConversationId(sessionIdRef.current);
      refreshConversations();
    } catch (e) {
      setError(translateError(e instanceof Error ? e.message : 'UNKNOWN'));
    } finally {
      setIsLoading(false);
    }
  }, [translateError, refreshConversations]);

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMsg]);
    setLastSendNonce((n) => n + 1);
    await runQuery(trimmed);
  }, [isLoading, runQuery]);

  // Re-sends the last user question of the conversation (e.g. after a network
  // failure) without making the user retype it.
  const retry = useCallback(async () => {
    if (isLoading) return;
    let lastQuery: string | null = null;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        lastQuery = messages[i].content;
        break;
      }
    }
    if (!lastQuery) return;
    await runQuery(lastQuery);
  }, [isLoading, messages, runQuery]);

  const sendVoice = useCallback(async (text: string): Promise<string | null> => {
    const trimmed = text.trim();
    if (!trimmed) return null;
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    setLastSendNonce((n) => n + 1);

    try {
      const data = await sendVoiceMessage(sessionIdRef.current, trimmed, 'fabric');
      const parsed = parseAssistantContent(data.answer);
      const cleanAnswer = parsed.answer || data.answer;
      const aiMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: cleanAnswer,
        timestamp: new Date(),
        isNew: true,
      };
      setMessages(prev => [...prev, aiMsg]);
      setActiveConversationId(sessionIdRef.current);
      refreshConversations();
      return cleanAnswer;
    } catch (e) {
      setError(translateError(e instanceof Error ? e.message : 'UNKNOWN'));
      return null;
    }
  }, [translateError, refreshConversations]);

  const clear = useCallback(async () => {
    try {
      await resetChat(sessionIdRef.current, 'fabric');
    } catch {
      // silent
    }
    setMessages([]);
    setError(null);
  }, []);

  const newConversation = useCallback(async () => {
    const newId = resetSessionId();
    sessionIdRef.current = newId;
    setSessionId(newId);
    setMessages([]);
    setError(null);
    setActiveConversationId(null);
  }, []);

  const switchConversation = useCallback(async (targetSessionId: string) => {
    if (targetSessionId === sessionIdRef.current && activeConversationId === targetSessionId) {
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const history = await fetchConversationMessages(targetSessionId);
      const sorted = [...history].sort((a, b) => a.message_order - b.message_order);

      const rebuilt: Message[] = sorted.map((row) => {
        const ts = row.created_at ? new Date(row.created_at) : new Date();
        if (row.role === 'assistant') {
          const parsed = parseAssistantContent(row.content);
          return {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: parsed.answer,
            timestamp: ts,
            analysisType: parsed.analysisType ?? null,
            analytics: parsed.analytics ?? null,
            nextStepSuggestions: parsed.nextStepSuggestions,
            visual: parsed.visual ?? null,
          };
        }
        return {
          id: crypto.randomUUID(),
          role: 'user',
          content: row.content,
          timestamp: ts,
        };
      });

      sessionIdRef.current = targetSessionId;
      setSessionId(targetSessionId);
      setMessages(rebuilt);
      setActiveConversationId(targetSessionId);
      setHistoryLoadNonce((n) => n + 1);
    } catch (e) {
      setError(translateError(e instanceof Error ? e.message : 'UNKNOWN'));
    } finally {
      setIsLoading(false);
    }
  }, [activeConversationId, translateError]);

  const removeConversation = useCallback(async (targetSessionId: string) => {
    try {
      await deleteConversationApi(targetSessionId);
    } catch {
      // best-effort
    }
    await refreshConversations();
    if (targetSessionId === activeConversationId || targetSessionId === sessionIdRef.current) {
      const newId = resetSessionId();
      sessionIdRef.current = newId;
      setSessionId(newId);
      setMessages([]);
      setError(null);
      setActiveConversationId(null);
    }
  }, [activeConversationId, refreshConversations]);

  const renameConversation = useCallback(async (
    targetSessionId: string,
    newTitle: string
  ) => {
    try {
      await renameConversationApi(targetSessionId, newTitle);
      await refreshConversations();
    } catch {
      // silent
    }
  }, [refreshConversations]);

  return {
    messages,
    isLoading,
    error,
    send,
    retry,
    sendVoice,
    clear,
    newConversation,
    conversations,
    activeConversationId,
    switchConversation,
    removeConversation,
    renameConversation,
    sessionId,
    lastSendNonce,
    historyLoadNonce,
  };
}
