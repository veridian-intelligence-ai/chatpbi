import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, ArrowLeft } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';
import { DottedSurface } from '@/components/ui/dotted-surface';
import { useLanguage } from '@/i18n/LanguageContext';
import { resetPasswordRequest } from '@/lib/auth';
import { validateNewPassword, type ResetPasswordError } from '@/lib/passwordReset';
import type { TranslationKey } from '@/i18n/translations';

const VALIDATION_KEYS: Record<ResetPasswordError, TranslationKey> = {
  minLength: 'reset.validation.minLength',
  mismatch: 'reset.validation.mismatch',
};

export default function ResetPasswordPage() {
  const { t } = useLanguage();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';

  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const validationError = validateNewPassword({ next, confirm });
    if (validationError) {
      setError(t(VALIDATION_KEYS[validationError]));
      return;
    }

    setIsLoading(true);
    const result = await resetPasswordRequest(token, next);
    setIsLoading(false);

    if (result.ok) {
      setDone(true);
      return;
    }
    // 400 = invalid/expired token; 429 (rate limit) and the rest are generic.
    const status = 'status' in result ? result.status : 0;
    setError(status === 400 ? t('reset.error.invalidToken') : t('reset.error.generic'));
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
                  {t('reset.title')}
                </h1>
                <p className="text-[11px] text-muted-foreground mt-0.5 leading-tight">
                  {t('reset.subtitle')}
                </p>
              </div>
            </div>

            {!token ? (
              <p className="text-[13px] text-destructive font-medium animate-fade-in">
                {t('reset.missingToken')}
              </p>
            ) : done ? (
              <p className="text-[13px] text-foreground/80 leading-relaxed animate-fade-in">
                {t('reset.success')}
              </p>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="text-[11px] font-semibold text-foreground/70 mb-1.5 block">
                    {t('reset.field.new')}
                  </label>
                  <div className="relative">
                    <input
                      type={show ? 'text' : 'password'}
                      value={next}
                      onChange={(e) => setNext(e.target.value)}
                      placeholder={t('reset.field.newPlaceholder')}
                      className="w-full h-11 px-3.5 pr-10 rounded-lg border border-border bg-background text-[16px] text-foreground placeholder:text-muted-foreground/40 outline-none focus:border-primary/30 transition-colors"
                      autoComplete="new-password"
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={() => setShow((s) => !s)}
                      aria-label={t('reset.toggleVisibility')}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                    >
                      {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-foreground/70 mb-1.5 block">
                    {t('reset.field.confirm')}
                  </label>
                  <input
                    type={show ? 'text' : 'password'}
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    placeholder={t('reset.field.confirmPlaceholder')}
                    className="w-full h-11 px-3.5 rounded-lg border border-border bg-background text-[16px] text-foreground placeholder:text-muted-foreground/40 outline-none focus:border-primary/30 transition-colors"
                    autoComplete="new-password"
                  />
                </div>

                {error && (
                  <p className="text-[11px] text-destructive font-medium animate-fade-in">{error}</p>
                )}

                <button
                  type="submit"
                  disabled={!next || !confirm || isLoading}
                  className="w-full h-11 rounded-lg bg-primary text-primary-foreground text-[14px] font-semibold shadow-[0_8px_24px_-8px_hsl(var(--primary)/0.6)] disabled:opacity-40 disabled:shadow-none hover:bg-primary/90 transition-all"
                >
                  {isLoading ? t('reset.submitting') : t('reset.submit')}
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
              {t('reset.backToLogin')}
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
