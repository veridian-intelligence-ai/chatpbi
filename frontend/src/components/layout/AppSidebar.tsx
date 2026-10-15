import { useState, useEffect, useRef } from 'react';
import {
  Plus,
  Building2,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Trash2,
  X,
  LogOut,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { ptBR, enUS } from 'date-fns/locale';
import { useAuth } from '@/hooks/useAuth';
import { Logo } from '@/components/brand/Logo';
import { type Conversation } from '@/hooks/useChat';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useLanguage } from '@/i18n/LanguageContext';
import { useModelInfo } from '@/hooks/useModelInfo';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { APP_NAME } from '@/config/app';

interface AppSidebarProps {
  onNewConversation: () => void;
  conversations: Conversation[];
  activeConversationId: string | null;
  onSwitchConversation: (sessionId: string) => void;
  onDeleteConversation: (sessionId: string) => void;
  onRenameConversation: (sessionId: string, newTitle: string) => void;
  onClose?: () => void;
  isMobile?: boolean;
}

export function AppSidebar({
  onNewConversation,
  conversations,
  activeConversationId,
  onSwitchConversation,
  onDeleteConversation,
  onRenameConversation,
  onClose,
  isMobile,
}: AppSidebarProps) {
  const { logout, companyName, userName } = useAuth();
  const { t, language } = useLanguage();
  const modelInfo = useModelInfo();
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState<string>('');
  const renameInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (renameTarget && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renameTarget]);

  const startRename = (sessionId: string, currentTitle: string) => {
    setRenameTarget(sessionId);
    setRenameValue(currentTitle);
  };

  const commitRename = () => {
    if (!renameTarget) return;
    const trimmed = renameValue.trim();
    const original = conversations.find((c) => c.session_id === renameTarget)?.title ?? '';
    if (trimmed && trimmed !== original) {
      onRenameConversation(renameTarget, trimmed);
    }
    setRenameTarget(null);
    setRenameValue('');
  };

  const cancelRename = () => {
    setRenameTarget(null);
    setRenameValue('');
  };

  const dateLocale = language === 'pt-BR' ? ptBR : enUS;

  const formatTimestamp = (iso: string): string => {
    if (!iso) return '';
    const date = new Date(iso);
    if (isNaN(date.getTime())) return '';
    const ageMs = Date.now() - date.getTime();
    if (ageMs < 60_000) return t('sidebar.timeNow');
    return formatDistanceToNow(date, { addSuffix: true, locale: dateLocale });
  };

  return (
    <aside className="w-[272px] h-full flex flex-col bg-sidebar shrink-0">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Logo className="w-7 h-7 text-primary" />
          <div>
            <h1 className="text-[14px] font-medium tracking-tight text-sidebar-foreground leading-none">{APP_NAME}</h1>
            <p className="text-[11px] text-sidebar-muted mt-1">Intelligence</p>
          </div>
        </div>
        {isMobile && onClose && (
          <button onClick={onClose} className="text-sidebar-muted hover:text-sidebar-foreground p-1">
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* New conversation */}
      <div className="px-3 pb-3">
        <button
          onClick={() => {
            onNewConversation();
            if (isMobile && onClose) onClose();
          }}
          className="w-full flex items-center justify-center gap-2 text-[13px] font-medium h-9 rounded-lg border border-sidebar-border text-sidebar-foreground bg-transparent hover:bg-sidebar-accent transition-colors duration-150"
          style={{ borderWidth: '1px' }}
        >
          <Plus className="h-3.5 w-3.5" />
          {t('sidebar.newConversation')}
        </button>
      </div>

      <div className="px-4 py-2 text-xs text-muted-foreground border-b border-border">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[hsl(var(--ring))] inline-block" />
          <span>{modelInfo.source}</span>
        </div>
        {modelInfo.name && (
          <div className="pl-4 text-muted-foreground/70">
            {modelInfo.name}
          </div>
        )}
      </div>

      {/* Conversations */}
      <div className="px-3 pt-3 flex-1 min-h-0 flex flex-col">
        <p className="text-[11px] text-sidebar-muted px-3 mb-1.5">{t('sidebar.conversations')}</p>
        <ScrollArea className="flex-1">
          <div className="space-y-0.5 pb-2">
            {conversations.length === 0 && (
              <p className="text-[12px] text-sidebar-muted/60 px-3 py-2">{t('sidebar.noConversations')}</p>
            )}
            {conversations.map((conv) => {
              const isActive = conv.session_id === activeConversationId;
              const isRenaming = renameTarget === conv.session_id;
              return (
                <div
                  key={conv.session_id}
                  className="group grid w-full min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-1"
                >
                  <div
                    role="button"
                    tabIndex={isRenaming ? -1 : 0}
                    onClick={() => {
                      if (isActive || isRenaming) return;
                      onSwitchConversation(conv.session_id);
                      if (isMobile && onClose) onClose();
                    }}
                    onKeyDown={(e) => {
                      if (isRenaming) return;
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        if (isActive) return;
                        onSwitchConversation(conv.session_id);
                        if (isMobile && onClose) onClose();
                      }
                    }}
                    className={`flex min-w-0 items-center gap-2 overflow-hidden px-3 py-2 rounded-lg text-[13px] cursor-pointer transition-colors duration-150 ${
                      isActive
                        ? 'bg-sidebar-accent text-sidebar-foreground'
                        : 'text-sidebar-muted hover:bg-sidebar-accent/60 hover:text-sidebar-foreground'
                    }`}
                  >
                    <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-60" />
                    <div className="min-w-0 flex-1 overflow-hidden">
                      {isRenaming ? (
                        <input
                          ref={renameInputRef}
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            e.stopPropagation();
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              commitRename();
                            } else if (e.key === 'Escape') {
                              e.preventDefault();
                              cancelRename();
                            }
                          }}
                          onBlur={commitRename}
                          className="w-full bg-transparent border border-sidebar-border rounded px-1.5 py-0.5 text-[13px] text-sidebar-foreground outline-none focus:border-sidebar-foreground/40 leading-tight"
                        />
                      ) : (
                        <p className="truncate leading-tight">{conv.title}</p>
                      )}
                      {conv.updated_at && !isRenaming && (
                        <p className="text-[10px] text-sidebar-muted/70 truncate mt-0.5 leading-none">
                          {formatTimestamp(conv.updated_at)}
                        </p>
                      )}
                    </div>
                  </div>

                  <div
                    className={`flex items-center transition-opacity ${
                      isRenaming ? 'opacity-0 pointer-events-none' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100 data-[state=open]:opacity-100'
                    }`}
                  >
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          onClick={(e) => e.stopPropagation()}
                          className="p-1.5 rounded-md hover:bg-sidebar-accent text-sidebar-muted hover:text-sidebar-foreground transition-colors"
                          aria-label={`${t('sidebar.rename')} / ${t('sidebar.delete')}`}
                        >
                          <MoreHorizontal className="h-3.5 w-3.5" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-40">
                        <DropdownMenuItem
                          onSelect={(e) => {
                            e.preventDefault();
                            startRename(conv.session_id, conv.title);
                          }}
                        >
                          <Pencil className="h-3.5 w-3.5 mr-2" />
                          {t('sidebar.rename')}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onSelect={(e) => {
                            e.preventDefault();
                            setDeleteTarget(conv.session_id);
                          }}
                          className="text-destructive focus:text-destructive"
                        >
                          <Trash2 className="h-3.5 w-3.5 mr-2" />
                          {t('sidebar.delete')}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </div>

      {/* Footer */}
      <div className="px-3 py-3" style={{ borderTop: '0.5px solid hsl(var(--sidebar-border))' }}>
        <div className="flex items-center gap-2.5 px-2 py-1">
          <div className="w-6 h-6 rounded-md bg-sidebar-accent flex items-center justify-center">
            <Building2 className="h-3 w-3 text-sidebar-muted" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[12px] text-sidebar-foreground truncate leading-none">{companyName || t('sidebar.company')}</p>
            <p className="text-[11px] text-sidebar-muted mt-1 leading-none truncate">{userName || t('sidebar.workspace')}</p>
          </div>
          <button
            onClick={logout}
            className="p-1.5 rounded-md text-sidebar-muted hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
            aria-label={t('sidebar.logout')}
            title={t('sidebar.logout')}
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Delete confirmation dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('sidebar.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('sidebar.deleteDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('sidebar.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleteTarget) {
                  onDeleteConversation(deleteTarget);
                  setDeleteTarget(null);
                }
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('sidebar.confirmDelete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  );
}
