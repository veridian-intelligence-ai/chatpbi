import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Lock, Eye, EyeOff } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';
import { DottedSurface } from '@/components/ui/dotted-surface';
import { useLanguage } from '@/i18n/LanguageContext';
import { useAuth } from '@/hooks/useAuth';
import type { TranslationKey } from '@/i18n/translations';
import { APP_NAME } from '@/config/app';

/** Maps the `AUTH_ERROR:<status>` from the password sign-in to a UI message. */
function loginErrorKey(error?: string): TranslationKey {
  if (error?.includes('AUTH_ERROR:401')) return 'login.error.invalidCredentials';
  if (error?.includes('AUTH_ERROR:403')) return 'login.error.notProvisioned';
  return 'login.error.generic';
}

export default function LoginPage() {
  const { loginWithPassword } = useAuth();
  const { t } = useLanguage();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    const result = await loginWithPassword(email, password);
    if (!result.ok) {
      setError(t(loginErrorKey(result.error)));
    }
    setIsLoading(false);
  };

  return (
    <div className="relative min-h-[100dvh] bg-background overflow-hidden">
      <DottedSurface />
      <div className="absolute inset-0 pointer-events-none bg-gradient-to-t from-background via-background/60 to-transparent" />

      <div className="relative min-h-[100dvh] flex items-center justify-center px-4">
        <div className="w-full max-w-[400px]">
          {/* Login form */}
          <div className="w-full">
            <div className="bg-card/80 backdrop-blur-sm border border-border rounded-2xl p-6 shadow-sm">
              <div className="flex items-center gap-3 pb-5 mb-5 border-b border-border/60">
                <Logo className="w-9 h-9 shrink-0 text-primary" />
                <div className="min-w-0">
                  <h1 className="text-[15px] font-bold tracking-tight text-foreground leading-tight">
                    {APP_NAME}
                  </h1>
                  <p className="text-[11px] text-muted-foreground mt-0.5 leading-tight">
                    {t('login.brand.subtitle')}
                  </p>
                </div>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="text-[11px] font-semibold text-foreground/70 mb-1.5 block">
                    {t('login.field.email')}
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={t('login.field.emailPlaceholder')}
                    className="w-full h-11 px-3.5 rounded-lg border border-border bg-background text-[16px] text-foreground placeholder:text-muted-foreground/40 outline-none focus:border-primary/30 transition-colors"
                    autoComplete="email"
                    autoFocus
                  />
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-foreground/70 mb-1.5 block">
                    {t('login.field.password')}
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={t('login.field.passwordPlaceholder')}
                      className="w-full h-11 px-3.5 pr-10 rounded-lg border border-border bg-background text-[16px] text-foreground placeholder:text-muted-foreground/40 outline-none focus:border-primary/30 transition-colors"
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                {error && (
                  <p className="text-[11px] text-destructive font-medium animate-fade-in">{error}</p>
                )}

                <button
                  type="submit"
                  disabled={!email.trim() || !password || isLoading}
                  className="w-full h-11 rounded-lg bg-primary text-primary-foreground text-[14px] font-semibold shadow-[0_8px_24px_-8px_hsl(var(--primary)/0.6)] disabled:opacity-40 disabled:shadow-none hover:bg-primary/90 transition-all"
                >
                  {isLoading ? t('login.submitting') : t('login.submit')}
                </button>

                <div className="flex justify-center">
                  <Link
                    to="/forgot-password"
                    className="text-[11px] text-muted-foreground/70 hover:text-muted-foreground transition-colors"
                  >
                    {t('login.forgotPassword')}
                  </Link>
                </div>

                <div className="flex items-center justify-center gap-1.5 pt-1">
                  <Lock className="h-3 w-3 text-muted-foreground/60" />
                  <p className="text-[10px] text-muted-foreground/70">
                    {t('login.restricted')}
                  </p>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
