import { RotateCcw, Circle, Menu, Sun, Moon } from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';
import { useLanguage } from '@/i18n/LanguageContext';
import { useAuth } from '@/hooks/useAuth';

interface AppHeaderProps {
  onClear: () => void;
  hasMessages: boolean;
  onToggleSidebar?: () => void;
  moduleName?: string;
}

export function AppHeader({ onClear, hasMessages, onToggleSidebar, moduleName }: AppHeaderProps) {
  const { theme, toggle: toggleTheme } = useTheme();
  const { t } = useLanguage();
  const { companyName } = useAuth();

  return (
    <header className="h-14 bg-background flex items-center justify-between px-4 md:px-6 shrink-0">
      <div className="flex items-center gap-3">
        {onToggleSidebar && (
          <button
            onClick={onToggleSidebar}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            aria-label={t('header.toggleSidebar')}
          >
            <Menu className="h-4 w-4" />
          </button>
        )}
        <h2 className="text-[14px] text-muted-foreground font-normal hidden sm:block">
          {t('header.subtitle')}
        </h2>
        <div className="flex items-center gap-1.5">
          <Circle className="h-1.5 w-1.5 fill-primary text-primary status-pulse" />
          <span className="text-[13px] text-muted-foreground">{moduleName ?? t('module.fabric.name')}</span>
          {companyName && (
            <span className="text-[13px] text-muted-foreground/60 hidden sm:inline">· {companyName}</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {hasMessages && (
          <button
            onClick={onClear}
            className="text-[13px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 h-8 px-2 rounded-md hover:bg-muted transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{t('header.clear')}</span>
          </button>
        )}
        <button
          onClick={toggleTheme}
          className="text-muted-foreground hover:text-foreground inline-flex items-center justify-center h-8 w-8 rounded-md hover:bg-muted transition-colors"
          aria-label={theme === 'dark' ? t('header.lightMode') : t('header.darkMode')}
        >
          {theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
        </button>
      </div>
    </header>
  );
}
