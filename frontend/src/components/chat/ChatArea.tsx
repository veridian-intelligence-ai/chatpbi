import { useRef, useEffect, useLayoutEffect, useState, useMemo, useCallback } from 'react';
import { Message } from '@/hooks/useChat';
import { ChatMessage, TypingIndicator } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { EmptyState } from './EmptyState';
import { VoiceMode } from './VoiceMode';
import { AlertCircle, RefreshCw } from 'lucide-react';
import type { ModuleConfig } from '@/lib/modules';
import { useIsMobile } from '@/hooks/use-mobile';
import { usePullToRefresh } from '@/hooks/usePullToRefresh';
import { useLanguage } from '@/i18n/LanguageContext';

interface ChatAreaProps {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  onSend: (message: string) => void;
  onRetry?: () => void;
  onSendVoice: (message: string) => Promise<string | null>;
  module: ModuleConfig;
  sessionId: string;
  lastSendNonce: number;
  historyLoadNonce: number;
}

const SCROLL_PADDING = 24; // matches the scroll container's py-6 (1.5rem)

export function ChatArea({ messages, isLoading, error, onSend, onRetry, onSendVoice, module, sessionId, lastSendNonce, historyLoadNonce }: ChatAreaProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const lastUserRef = useRef<HTMLDivElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);
  // True while the latest turn is pinned (question anchored to the top). The
  // reserved spacer is only active in this state, so loaded history and cleared
  // conversations never get phantom blank space at the bottom.
  const anchoredRef = useRef(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const isMobile = useIsMobile();
  const { t } = useLanguage();
  const canRetry = messages.some((m) => m.role === 'user');

  const { ref: ptrRef, pull, refreshing, threshold } = usePullToRefresh<HTMLDivElement>({
    enabled: isMobile,
  });

  // Merge refs
  const setScrollRefs = (node: HTMLDivElement | null) => {
    scrollRef.current = node;
    ptrRef.current = node;
  };

  const isEmpty = messages.length === 0;

  // Id of the most recent user message — the bubble we pin to the top.
  const lastUserId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') return messages[i].id;
    }
    return null;
  }, [messages]);

  // Sizes the bottom spacer so the pinned question can reach the top even when
  // the answer is short: reserve just enough that the content below the question
  // fills the viewport. Idempotent and a no-op while not anchored, so it is safe
  // to call repeatedly from a ResizeObserver.
  const recomputeSpacer = useCallback(() => {
    const container = scrollRef.current;
    const spacer = spacerRef.current;
    if (!container || !spacer) return;
    const userEl = lastUserRef.current;
    if (!anchoredRef.current || !userEl) {
      if (spacer.style.minHeight !== '0px') spacer.style.minHeight = '0px';
      return;
    }
    const currentSpacer = spacer.offsetHeight;
    const naturalBelow = container.scrollHeight - userEl.offsetTop - currentSpacer;
    const next = Math.max(0, Math.round(container.clientHeight - SCROLL_PADDING - naturalBelow));
    if (Math.abs(next - currentSpacer) > 1) {
      spacer.style.minHeight = `${next}px`;
    }
  }, []);

  // Fresh send (send / sendVoice): pin the user's bubble to the top and reserve
  // space below it. Intentionally NOT re-run on response arrival or while the
  // typewriter grows, so the answer unfolds beneath a stationary question.
  useLayoutEffect(() => {
    if (lastSendNonce === 0) return;
    const container = scrollRef.current;
    const userEl = lastUserRef.current;
    if (!container || !userEl) return;
    anchoredRef.current = true;
    recomputeSpacer();
    container.scrollTop = Math.max(0, userEl.offsetTop - SCROLL_PADDING);
  }, [lastSendNonce, recomputeSpacer]);

  // History load / conversation switch: drop the reserve and jump to the bottom,
  // preserving the previous always-at-bottom behavior for existing threads.
  useLayoutEffect(() => {
    if (historyLoadNonce === 0) return;
    const container = scrollRef.current;
    if (!container) return;
    anchoredRef.current = false;
    if (spacerRef.current) spacerRef.current.style.minHeight = '0px';
    container.scrollTop = container.scrollHeight;
  }, [historyLoadNonce]);

  // Keep the reserve correct as the viewport resizes (window / sidebar) and as
  // the turn's content grows (typewriter, then the visual/suggestions that mount
  // after it). Recompute only — never re-scroll — so the anchor never jumps.
  useEffect(() => {
    const container = scrollRef.current;
    if (isEmpty || !container) return;
    const ro = new ResizeObserver(() => recomputeSpacer());
    ro.observe(container);
    if (contentRef.current) ro.observe(contentRef.current);
    return () => ro.disconnect();
  }, [isEmpty, recomputeSpacer]);

  const openVoice = () => setVoiceOpen(true);

  const progress = Math.min(1, pull / threshold);
  const showPtr = pull > 0 || refreshing;

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-background">
      {isEmpty ? (
        <EmptyState onSendQuery={onSend} isLoading={isLoading} module={module} sessionId={sessionId} onOpenVoice={openVoice} />
      ) : (
        <>
          <div ref={setScrollRefs} className="flex-1 overflow-y-auto px-4 md:px-6 py-6 relative">
            {showPtr && (
              <div
                className="pointer-events-none absolute left-0 right-0 top-0 flex items-center justify-center z-10"
                style={{
                  height: `${refreshing ? threshold : pull}px`,
                  opacity: refreshing ? 1 : progress,
                }}
              >
                <RefreshCw
                  className={`h-4 w-4 text-muted-foreground ${refreshing ? 'animate-spin' : ''}`}
                  style={{ transform: refreshing ? undefined : `rotate(${progress * 270}deg)` }}
                />
              </div>
            )}
            <div
              ref={contentRef}
              className="max-w-[760px] mx-auto space-y-6"
              style={{ transform: showPtr ? `translateY(${refreshing ? threshold : pull}px)` : undefined, transition: refreshing ? 'transform 150ms' : undefined }}
            >
              {messages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  ref={msg.id === lastUserId ? lastUserRef : undefined}
                  message={msg}
                  suggestions={msg.nextStepSuggestions}
                  onSendQuery={msg.nextStepSuggestions?.length ? onSend : undefined}
                />
              ))}
              {isLoading && <TypingIndicator />}
              {error && (
                <div className="flex flex-col gap-2 px-4 py-3 rounded-xl border border-destructive/20 text-[13px] text-destructive animate-fade-in">
                  <div className="flex items-start gap-2.5">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                    <p>{error}</p>
                  </div>
                  {onRetry && canRetry && (
                    <button
                      type="button"
                      onClick={onRetry}
                      disabled={isLoading}
                      className="self-start inline-flex items-center gap-1.5 rounded-md border border-destructive/30 px-2.5 py-1 text-[12px] font-medium transition-colors hover:bg-destructive/10 disabled:pointer-events-none disabled:opacity-50"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      {t('chat.retry')}
                    </button>
                  )}
                </div>
              )}
            </div>
            {/* Reserved space so the pinned question can reach the top even when
                the answer is short. Sized imperatively by recomputeSpacer; kept
                outside the list wrapper so it never re-triggers the observer. */}
            <div ref={spacerRef} aria-hidden="true" style={{ minHeight: 0 }} />
          </div>
          <ChatInput onSend={onSend} isLoading={isLoading} module={module} onOpenVoice={openVoice} />
        </>
      )}
      <VoiceMode
        open={voiceOpen}
        onClose={() => setVoiceOpen(false)}
        module={module}
        onSendVoice={onSendVoice}
      />
    </div>
  );
}
