import { useChat } from '@/hooks/useChat';
import { AppSidebar } from '@/components/layout/AppSidebar';
import { AppHeader } from '@/components/layout/AppHeader';
import { ChatArea } from '@/components/chat/ChatArea';
import { useSidebarState } from '@/hooks/useSidebar';
import { useIsMobile } from '@/hooks/use-mobile';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { MODULE_CONFIG } from '@/lib/modules';
import { useLanguage } from '@/i18n/LanguageContext';

const Index = () => {
  const {
    messages,
    isLoading,
    error,
    send,
    retry,
    sendVoice,
    clear,
    newConversation,
    conversations,
    activeConversationId,
    switchConversation,
    removeConversation,
    renameConversation,
    sessionId,
    lastSendNonce,
    historyLoadNonce,
  } = useChat();

  const { isOpen, toggle, close } = useSidebarState();
  const isMobile = useIsMobile();
  const { t } = useLanguage();

  const sidebarProps = {
    onNewConversation: newConversation,
    conversations,
    activeConversationId,
    onSwitchConversation: switchConversation,
    onDeleteConversation: removeConversation,
    onRenameConversation: renameConversation,
  };

  return (
    <div className="h-[100dvh] flex bg-background overflow-hidden">
      {!isMobile && isOpen && <AppSidebar {...sidebarProps} />}

      {isMobile && (
        <Sheet open={isOpen} onOpenChange={(open) => !open && close()}>
          <SheetContent side="left" className="p-0 w-[280px] bg-sidebar border-sidebar-border [&>button]:hidden">
            <AppSidebar {...sidebarProps} onClose={close} isMobile />
          </SheetContent>
        </Sheet>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <AppHeader
          onClear={clear}
          hasMessages={messages.length > 0}
          onToggleSidebar={toggle}
          moduleName={t(MODULE_CONFIG.nameKey)}
        />
        <div className="flex-1 flex min-h-0">
          <ChatArea
            messages={messages}
            isLoading={isLoading}
            error={error}
            onSend={send}
            onRetry={retry}
            onSendVoice={sendVoice}
            module={MODULE_CONFIG}
            sessionId={sessionId}
            lastSendNonce={lastSendNonce}
            historyLoadNonce={historyLoadNonce}
          />
        </div>
      </div>
    </div>
  );
};

export default Index;
