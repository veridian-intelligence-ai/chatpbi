import { useState, useRef, useEffect } from 'react';
import { ArrowUp, Mic } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';
import type { ModuleConfig } from '@/lib/modules';
import { useLanguage } from '@/i18n/LanguageContext';
import { fetchSuggestions } from '@/lib/api';

interface EmptyStateProps {
  onSendQuery: (query: string) => void;
  isLoading?: boolean;
  module: ModuleConfig;
  sessionId: string;
  onOpenVoice?: () => void;
}

export function EmptyState({ onSendQuery, isLoading = false, module, sessionId, onOpenVoice }: EmptyStateProps) {
  const { t, language } = useLanguage();
  const [suggestions, setSuggestions] = useState<string[] | null>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setSuggestionsLoading(true);
    setSuggestions(null);
    const langCode: 'pt' | 'en' = language.toLowerCase().startsWith('pt') ? 'pt' : 'en';
    fetchSuggestions(sessionId, 'fabric', langCode)
      .then((list) => {
        if (cancelled) return;
        setSuggestions(list && list.length > 0 ? list.slice(0, 6) : null);
      })
      .catch(() => {
        if (cancelled) return;
        setSuggestions(null);
      })
      .finally(() => {
        if (!cancelled) setSuggestionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, module.id, language]);
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function getGreeting() {
    const h = new Date().getHours();
    if (h < 12) return t('greeting.morning');
    if (h < 18) return t('greeting.afternoon');
    return t('greeting.evening');
  }

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 160) + 'px';
    }
  }, [value]);

  const submit = () => {
    if (!value.trim() || isLoading) return;
    onSendQuery(value);
    setValue('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const hasText = value.trim().length > 0;

  return (
    <div className="flex-1 flex items-center justify-center px-4 md:px-8 overflow-y-auto">
      <div className="max-w-[760px] w-full py-10">
        <div className="flex items-center justify-center gap-3 mb-3 animate-fade-in">
          <Logo className="h-7 w-7 text-primary" />
          <h1 className="text-[28px] font-medium text-foreground tracking-[-0.01em] leading-none">
            {getGreeting()}
          </h1>
        </div>

        <div className="text-center mb-8 animate-fade-in">
          <p className="text-[15px]">
            <span className="text-foreground font-medium">{t(module.hero.titleKey)}</span>
            <span className="text-muted-foreground"> {t(module.hero.subtitleKey)}</span>
          </p>
        </div>

        <div className="bg-background border border-border rounded-2xl px-4 py-3 focus-within:border-foreground/30 transition-colors duration-150 animate-fade-in">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t(module.placeholderKey)}
            rows={1}
            className="w-full bg-transparent text-[16px] md:text-[15px] text-foreground placeholder:text-muted-foreground/70 resize-none outline-none leading-relaxed"
          />
          <div className="flex items-center justify-end gap-2 pt-2">
            {onOpenVoice && (
              <button
                onClick={onOpenVoice}
                type="button"
                className="w-7 h-7 rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors duration-150"
                aria-label="Voice mode"
              >
                <Mic className="h-4 w-4" strokeWidth={2} />
              </button>
            )}
            <button
              onClick={submit}
              disabled={!hasText || isLoading}
              className={`w-7 h-7 rounded-full flex items-center justify-center transition-all duration-150 ${
                hasText
                  ? 'bg-foreground text-background hover:opacity-90'
                  : 'bg-muted text-muted-foreground/60'
              }`}
              aria-label={t('chat.send')}
            >
              <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.5} />
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2 mt-5 animate-fade-in">
          {suggestionsLoading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-7 w-32 rounded-full bg-muted animate-pulse"
                style={{ width: `${96 + ((i * 23) % 80)}px` }}
              />
            ))
          ) : (
            (suggestions ?? module.suggestionKeys.map((k) => t(k))).map((label, idx) => (
              <button
                key={`${idx}-${label}`}
                onClick={() => onSendQuery(label)}
                className="text-[13px] text-muted-foreground hover:text-foreground bg-background hover:bg-muted/60 px-3 py-1.5 rounded-full border border-border transition-colors duration-150"
                style={{ borderWidth: '0.5px' }}
              >
                {label}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
