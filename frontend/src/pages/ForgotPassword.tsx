import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';
import { DottedSurface } from '@/components/ui/dotted-surface';
import { useLanguage } from '@/i18n/LanguageContext';
import { forgotPasswordRequest } from '@/lib/auth';

export default function ForgotPasswordPage() {
  const { t } = useLanguage();
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await forgotPasswordRequest(email.trim());
    } catch {
      // Anti-enumeration: never surface the outcome. The neutral message is
      // shown regardless of whether the request succeeded or even reached the
      // server, so a caller cannot tell whether the email exists.
    }
    setIsLoading(false);
    setSubmitted(true);
  };

  return (
    <div className="relative min-h-[100dvh] bg-background overflow-hidden">
      <DottedSurface />
      <div className="absolute inset-0 pointer-events-none bg-gradient-to-t from-background via-background/60 to-transparent" />

      <div className="relative min-h-[100dvh] flex items-center justify-center px-4">
        <div className="w-full max-w-[400px]">
          <div className="bg-card/80 backdrop-blur-sm border border-border rounded-2xl p-6 shadow-sm">
            <div className="flex items-center gap-3 pb-5 mb-5 border-b border-border/60">
              <Logo className="w-9 h-9 shrink-0 text-primary" />
              <div className="min-w-0">
                <h1 className="text-[15px] font-bold tracking-tight text-foreground leading-tight">
                  {t('forgot.title')}
                </h1>
                <p className="text-[11px] text-muted-foreground mt-0.5 leading-tight">
                  {t('forgot.subtitle')}
                </p>
              </div>
            </div>

            {submitted ? (
              <p className="text-[13px] text-foreground/80 leading-relaxed animate-fade-in">
                {t('forgot.neutral')}
              </p>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="text-[11px] font-semibold text-foreground/70 mb-1.5 block">
                    {t('forgot.field.email')}
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={t('forgot.field.emailPlaceholder')}
                    className="w-full h-11 px-3.5 rounded-lg border border-border bg-background text-[16px] text-foreground placeholder:text-muted-foreground/40 outline-none focus:border-primary/30 transition-colors"
                    autoComplete="email"
                    autoFocus
                  />
                </div>

                <button
                  type="submit"
                  disabled={!email.trim() || isLoading}
                  className="w-full h-11 rounded-lg bg-primary text-primary-foreground text-[14px] font-semibold shadow-[0_8px_24px_-8px_hsl(var(--primary)/0.6)] disabled:opacity-40 disabled:shadow-none hover:bg-primary/90 transition-all"
                >
                  {isLoading ? t('forgot.submitting') : t('forgot.submit')}
                </button>
              </form>
            )}
          </div>

          <div className="flex justify-center mt-5">
            <Link
              to="/login"
              className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground/70 hover:text-muted-foreground transition-colors"
            >
              <ArrowLeft className="h-3 w-3" />
              {t('forgot.backToLogin')}
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
