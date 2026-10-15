import { forwardRef, useState } from 'react';
import { Message } from '@/hooks/useChat';
import { Logo } from '@/components/brand/Logo';
import { ArrowUpRight } from 'lucide-react';
import { VeridianVisualRenderer } from './visuals/VeridianVisualRenderer';
import { TypewriterText } from './TypewriterText';
import { useLanguage } from '@/i18n/LanguageContext';
import { APP_NAME } from '@/config/app';

interface ChatMessageProps {
  message: Message;
  suggestions?: string[];
  onSendQuery?: (query: string) => void;
}

export const ChatMessage = forwardRef<HTMLDivElement, ChatMessageProps>(function ChatMessage(
  { message, suggestions, onSendQuery },
  ref,
) {
  const { t } = useLanguage();
  const isUser = message.role === 'user';
  const useTypewriter = !isUser && message.isNew === true;
  const [typingDone, setTypingDone] = useState(!useTypewriter);
  const showSuggestions = !isUser && suggestions && suggestions.length > 0 && onSendQuery;
  const revealExtras = !useTypewriter || typingDone;

  if (isUser) {
    return (
      <div ref={ref} className="flex justify-end animate-fade-in">
        <div className="max-w-[min(600px,85vw)]">
          <div className="bg-chat-user text-chat-user-foreground rounded-xl px-4 py-3 text-[15px] leading-[1.65]">
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={ref} className="flex justify-start animate-fade-in">
      <div className="w-full max-w-full">
        <div className="flex items-center gap-2 mb-2">
          <Logo className="w-4 h-4 opacity-80 text-primary" />
          <span className="text-[12px] text-muted-foreground">{APP_NAME}</span>
        </div>
        <div className="text-[15px] leading-[1.7] text-foreground">
          <TypewriterText
            text={message.content}
            enabled={useTypewriter}
            onDone={() => setTypingDone(true)}
          />
        </div>
        {revealExtras && <VeridianVisualRenderer visual={message.visual} />}
        {showSuggestions && revealExtras && (
          <div className="mt-4 animate-fade-in">
            <p className="text-[11px] text-muted-foreground mb-2">{t('chat.suggestedQuestions')}</p>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => onSendQuery(s)}
                  className="group inline-flex items-center gap-1.5 text-left text-[13px] text-muted-foreground hover:text-foreground bg-background hover:bg-muted/60 px-3 py-1.5 rounded-full border border-border transition-colors duration-150"
                  style={{ borderWidth: '0.5px' }}
                >
                  <span className="leading-snug">{s}</span>
                  <ArrowUpRight className="h-3 w-3 shrink-0 opacity-0 group-hover:opacity-60 transition-opacity duration-150" />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

export function TypingIndicator() {
  return (
    <div className="flex justify-start animate-fade-in">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Logo className="w-4 h-4 opacity-80 text-primary" />
          <span className="text-[12px] text-muted-foreground">{APP_NAME}</span>
        </div>
        <div className="flex items-center gap-1.5 py-2">
          <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 typing-dot" />
          <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 typing-dot" />
          <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 typing-dot" />
        </div>
      </div>
    </div>
  );
}
