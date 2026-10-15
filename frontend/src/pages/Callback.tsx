import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';
import { DottedSurface } from '@/components/ui/dotted-surface';
import { useLanguage } from '@/i18n/LanguageContext';
import { useAuth } from '@/hooks/useAuth';
import {
  parseCallbackParams,
  readAndClearState,
  validateState,
  classifyWorkosError,
  type WorkosCallbackError,
} from '@/lib/workos';
import type { TranslationKey } from '@/i18n/translations';
import { APP_NAME } from '@/config/app';

const CALLBACK_ERROR_KEYS: Record<WorkosCallbackError, TranslationKey> = {
  notProvisioned: 'callback.error.notProvisioned',
  expired: 'callback.error.expired',
  state: 'callback.error.state',
  generic: 'callback.error.generic',
};

export default function CallbackPage() {
  const { t } = useLanguage();
  const { loginWithWorkos } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<WorkosCallbackError | null>(null);
  const exchanged = useRef(false);

  useEffect(() => {
    // The authorization code is single-use; guard against a double run
    // (re-mount) consuming or replaying it.
    if (exchanged.current) return;
    exchanged.current = true;

    const { code, state } = parseCallbackParams(window.location.search);
    const storedState = readAndClearState();

    // Anti-CSRF: the state returned by AuthKit must match the one we stored
    // before the redirect. A mismatch (or missing value) drops back to login.
    if (!code || !validateState(state, storedState)) {
      setError('state');
      return;
    }

    loginWithWorkos(code).then((result) => {
      if (result.ok) {
        // Session is established; the /home route guard renders it for
        // authenticated users (and bounces to /login if the session is missing).
        navigate('/home', { replace: true });
      } else {
        setError(classifyWorkosError(result.error ?? ''));
      }
    });
  }, [loginWithWorkos, navigate]);

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
                  {APP_NAME}
                </h1>
                <p className="text-[11px] text-muted-foreground mt-0.5 leading-tight">
                  {t('login.brand.subtitle')}
                </p>
              </div>
            </div>

            {error ? (
              <div className="space-y-4">
                <p className="text-[13px] text-destructive font-medium animate-fade-in">
                  {t(CALLBACK_ERROR_KEYS[error])}
                </p>
                <Link
                  to="/login"
                  className="inline-flex items-center justify-center w-full h-11 rounded-lg border border-border bg-background/40 text-[13px] font-medium text-foreground/80 hover:bg-background hover:border-primary/30 transition-colors"
                >
                  {t('callback.backToLogin')}
                </Link>
              </div>
            ) : (
              <div className="flex items-center gap-2.5 py-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <p className="text-[13px]">{t('callback.loading')}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
