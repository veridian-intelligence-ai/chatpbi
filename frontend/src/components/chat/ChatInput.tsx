import { useState, useRef, useEffect } from "react";
import { ArrowUp, Mic } from "lucide-react";
import type { ModuleConfig } from "@/lib/modules";
import { useLanguage } from "@/i18n/LanguageContext";
import { APP_NAME } from '@/config/app';

// ---------------------------------------------------------------------------
// iOS Safari Audio Unlock
// ---------------------------------------------------------------------------
// iOS only permits audio.play() inside a synchronous user-gesture chain.
// We unlock the <audio> element here — at the mic button tap — which is the
// earliest and cleanest gesture available, before any awaits occur.
// ---------------------------------------------------------------------------

let globalAudioUnlocked = false;

async function unlockIOSAudio(): Promise<void> {
  if (globalAudioUnlocked) return;
  try {
    const AudioCtor: typeof AudioContext =
      (window as unknown as { AudioContext: typeof AudioContext }).AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (AudioCtor) {
      const ctx = new AudioCtor();
      if (ctx.state === "suspended") await ctx.resume();
      const buf = ctx.createBuffer(1, 1, 22050);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(0);
      await ctx.close();
    }
    // Create a throwaway <audio> and play a silent blob to mark the
    // audio subsystem as user-gesture-unlocked for this page session.
    const silence = new Blob(
      [new Uint8Array([255, 227, 24, 196, 0, 0, 0, 3, 72, 1, 64, 0, 0, 4, 132, 16, 31, 227, 192, 0, 0, 0, 0])],
      { type: "audio/mpeg" },
    );
    const url = URL.createObjectURL(silence);
    const tmp = new Audio(url);
    tmp.volume = 0;
    tmp.setAttribute("playsinline", "");
    try {
      await tmp.play();
      tmp.pause();
    } catch {
      /* noop */
    }
    URL.revokeObjectURL(url);
    globalAudioUnlocked = true;
  } catch {
    /* noop */
  }
}

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
  module?: ModuleConfig;
  onOpenVoice?: () => void;
}

export function ChatInput({ onSend, isLoading, module, onOpenVoice }: ChatInputProps) {
  const { t } = useLanguage();
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [value]);

  const handleSubmit = () => {
    if (!value.trim() || isLoading) return;
    onSend(value);
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Unlock iOS audio in the same gesture as opening the voice modal.
  // unlockIOSAudio() is async but called without await so the gesture
  // chain stays synchronous — iOS still counts this as user-initiated.
  const handleOpenVoice = () => {
    unlockIOSAudio();
    onOpenVoice?.();
  };

  const hasText = value.trim().length > 0;
  const placeholder = module ? t(module.placeholderKey) : t("module.fabric.placeholder");
  const moduleName = module ? t(module.nameKey) : t("module.fabric.name");

  return (
    <div className="bg-background px-4 md:px-6 pt-2 pb-3 safe-area-bottom">
      <div className="max-w-[760px] mx-auto">
        <div className="flex items-end gap-2 bg-background border border-border rounded-2xl px-4 py-3 focus-within:border-foreground/30 transition-colors duration-150">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={1}
            className="flex-1 bg-transparent text-[16px] md:text-[15px] text-foreground placeholder:text-muted-foreground/70 resize-none outline-none leading-relaxed py-0.5"
          />
          {onOpenVoice && (
            <button
              onClick={handleOpenVoice}
              type="button"
              className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors duration-150"
              aria-label="Voice mode"
            >
              <Mic className="h-4 w-4" strokeWidth={2} />
            </button>
          )}
          <button
            onClick={handleSubmit}
            disabled={!hasText || isLoading}
            className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-all duration-150 ${
              hasText ? "bg-foreground text-background hover:opacity-90" : "bg-muted text-muted-foreground/60"
            }`}
            aria-label={t("chat.send")}
          >
            <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.5} />
          </button>
        </div>
        <p className="text-center text-[11px] text-muted-foreground/60 mt-2 hidden sm:block">
          {APP_NAME} · {moduleName}
          {module?.source ? ` · ${module.source}` : ""}
        </p>
      </div>
    </div>
  );
}
