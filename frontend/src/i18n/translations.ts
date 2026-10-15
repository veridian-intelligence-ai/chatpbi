export type Language = 'pt-BR' | 'en-US';

export const translations = {
  'pt-BR': {
    // Sidebar
    'sidebar.newConversation': 'Nova conversa',
    'sidebar.modules': 'Módulos',
    'sidebar.conversations': 'Conversas',
    'sidebar.comingSoon': 'Em breve',
    'sidebar.workspace': 'Área de trabalho',
    'sidebar.company': 'Empresa',
    'sidebar.noConversations': 'Nenhuma conversa ainda',
    'sidebar.connected': 'Conectado',
    'sidebar.logout': 'Sair',
    'sidebar.rename': 'Renomear',
    'sidebar.delete': 'Excluir',
    'sidebar.deleteTitle': 'Excluir conversa',
    'sidebar.deleteDescription': 'Tem certeza que deseja excluir esta conversa? Esta ação não pode ser desfeita.',
    'sidebar.cancel': 'Cancelar',
    'sidebar.confirmDelete': 'Excluir',
    'sidebar.timeNow': 'Agora',

    // Header
    'header.subtitle': 'Converse com os dados da sua empresa',
    'header.clear': 'Limpar',
    'header.toggleSidebar': 'Alternar barra lateral',
    'header.lightMode': 'Ativar modo claro',
    'header.darkMode': 'Ativar modo escuro',

    // Greetings
    'greeting.morning': 'Bom dia',
    'greeting.afternoon': 'Boa tarde',
    'greeting.evening': 'Boa noite',

    // Module — Power BI (modelo semântico ativo no backend)
    'module.fabric.name': 'Dados do Power BI',
    'module.fabric.placeholder': 'Pergunte sobre os seus dados...',
    'module.fabric.hero.title': 'Converse com os dados do Power BI',
    'module.fabric.hero.subtitle': 'Faça perguntas em linguagem natural',

    // Chat
    'chat.send': 'Enviar mensagem',
    'chat.suggestedQuestions': 'Perguntas sugeridas',
    'chat.typing': 'Consultando...',
    'chat.retry': 'Tentar novamente',

    // Errors
    'error.serverCommunication': 'Erro na comunicação com o servidor',
    'error.timeout': 'A consulta demorou demais. Tente reformular a pergunta.',
    'error.resetConversation': 'Erro ao limpar a conversa',
    'toast.sessionCleared': 'Sessão limpa com sucesso.',

    // Login
    'login.brand.subtitle': 'Acesso à plataforma',
    'login.field.email': 'E-mail',
    'login.field.emailPlaceholder': 'seu@email.com',
    'login.field.password': 'Senha',
    'login.field.passwordPlaceholder': 'Digite sua senha',
    'login.submit': 'Entrar',
    'login.submitting': 'Entrando...',
    'login.forgotPassword': 'Esqueceu a senha?',
    'login.error.invalidCredentials': 'E-mail ou senha incorretos.',
    'login.error.notProvisioned': 'Sua conta ainda não tem acesso à plataforma. Fale com o administrador.',
    'login.error.generic': 'Não foi possível entrar. Tente novamente.',
    'login.restricted': 'Acesso restrito · apenas usuários autorizados',

    // WorkOS sign-in (SSO callback)
    'callback.loading': 'Concluindo o login...',
    'callback.error.notProvisioned': 'Sua conta ainda não tem acesso à plataforma. Fale com o administrador.',
    'callback.error.expired': 'Sessão expirada. Tente novamente.',
    'callback.error.state': 'Não foi possível validar o pedido de login. Tente novamente.',
    'callback.error.generic': 'Não foi possível entrar. Tente novamente.',
    'callback.backToLogin': 'Voltar ao login',

    // Forgot password (headless reset request)
    'forgot.title': 'Recuperar senha',
    'forgot.subtitle': 'Digite seu e-mail e enviaremos as instruções de recuperação.',
    'forgot.field.email': 'E-mail',
    'forgot.field.emailPlaceholder': 'seu@email.com',
    'forgot.submit': 'Enviar instruções',
    'forgot.submitting': 'Enviando...',
    'forgot.neutral': 'Se o e-mail existir, você vai receber as instruções de recuperação.',
    'forgot.backToLogin': 'Voltar ao login',

    // Reset password (headless, via e-mail token)
    'reset.title': 'Definir nova senha',
    'reset.subtitle': 'Escolha uma nova senha para a sua conta.',
    'reset.field.new': 'Nova senha',
    'reset.field.newPlaceholder': 'Pelo menos 10 caracteres',
    'reset.field.confirm': 'Confirmar nova senha',
    'reset.field.confirmPlaceholder': 'Repita a nova senha',
    'reset.toggleVisibility': 'Mostrar ou ocultar a senha',
    'reset.submit': 'Salvar nova senha',
    'reset.submitting': 'Salvando...',
    'reset.success': 'Senha alterada com sucesso. Você já pode entrar.',
    'reset.missingToken': 'Link de recuperação inválido. Peça um novo na tela de login.',
    'reset.validation.minLength': 'A senha deve ter pelo menos 10 caracteres.',
    'reset.validation.mismatch': 'As senhas não são iguais.',
    'reset.error.invalidToken': 'O link de recuperação é inválido ou expirou. Peça um novo.',
    'reset.error.generic': 'Não foi possível alterar a senha. Tente novamente.',
    'reset.backToLogin': 'Voltar ao login',
  },
  'en-US': {
    // Sidebar
    'sidebar.newConversation': 'New conversation',
    'sidebar.modules': 'Modules',
    'sidebar.conversations': 'Conversations',
    'sidebar.comingSoon': 'Coming soon',
    'sidebar.workspace': 'Workspace',
    'sidebar.company': 'Company',
    'sidebar.noConversations': 'No conversations yet',
    'sidebar.connected': 'Connected',
    'sidebar.logout': 'Sign out',
    'sidebar.rename': 'Rename',
    'sidebar.delete': 'Delete',
    'sidebar.deleteTitle': 'Delete conversation',
    'sidebar.deleteDescription': 'Are you sure you want to delete this conversation? This action cannot be undone.',
    'sidebar.cancel': 'Cancel',
    'sidebar.confirmDelete': 'Delete',
    'sidebar.timeNow': 'Now',

    // Header
    'header.subtitle': 'Talk to your data',
    'header.clear': 'Clear',
    'header.toggleSidebar': 'Toggle sidebar',
    'header.lightMode': 'Switch to light mode',
    'header.darkMode': 'Switch to dark mode',

    // Greetings
    'greeting.morning': 'Good morning',
    'greeting.afternoon': 'Good afternoon',
    'greeting.evening': 'Good evening',

    // Module — Power BI (active semantic model in the backend)
    'module.fabric.name': 'Power BI data',
    'module.fabric.placeholder': 'Ask about your data...',
    'module.fabric.hero.title': 'Talk to your Power BI data',
    'module.fabric.hero.subtitle': 'Ask questions in natural language',

    // Chat
    'chat.send': 'Send message',
    'chat.suggestedQuestions': 'Suggested questions',
    'chat.typing': 'Querying...',
    'chat.retry': 'Try again',

    // Errors
    'error.serverCommunication': 'Server communication error',
    'error.timeout': 'The query took too long. Try rephrasing your question.',
    'error.resetConversation': 'Failed to reset conversation',
    'toast.sessionCleared': 'Session cleared successfully.',

    // Login
    'login.brand.subtitle': 'Platform access',
    'login.field.email': 'Email',
    'login.field.emailPlaceholder': 'you@email.com',
    'login.field.password': 'Password',
    'login.field.passwordPlaceholder': 'Enter your password',
    'login.submit': 'Sign in',
    'login.submitting': 'Authenticating...',
    'login.forgotPassword': 'Forgot your password?',
    'login.error.invalidCredentials': 'Incorrect email or password.',
    'login.error.notProvisioned': 'Your account does not have access to the platform yet. Contact your administrator.',
    'login.error.generic': 'Could not sign in. Please try again.',
    'login.restricted': 'Restricted access · authorized users only',

    // WorkOS sign-in (SSO callback)
    'callback.loading': 'Completing sign-in...',
    'callback.error.notProvisioned': 'Your account does not have access to the platform yet. Contact your administrator.',
    'callback.error.expired': 'Session expired. Please try again.',
    'callback.error.state': 'Could not validate the sign-in request. Please try again.',
    'callback.error.generic': 'Could not sign in. Please try again.',
    'callback.backToLogin': 'Back to sign in',

    // Forgot password (headless reset request)
    'forgot.title': 'Recover password',
    'forgot.subtitle': 'Enter your email and we will send recovery instructions.',
    'forgot.field.email': 'Email',
    'forgot.field.emailPlaceholder': 'you@email.com',
    'forgot.submit': 'Send instructions',
    'forgot.submitting': 'Sending...',
    'forgot.neutral': 'If the email exists, you will receive recovery instructions.',
    'forgot.backToLogin': 'Back to sign in',

    // Reset password (headless, via email token)
    'reset.title': 'Set a new password',
    'reset.subtitle': 'Choose a new password for your account.',
    'reset.field.new': 'New password',
    'reset.field.newPlaceholder': 'At least 10 characters',
    'reset.field.confirm': 'Confirm new password',
    'reset.field.confirmPlaceholder': 'Repeat the new password',
    'reset.toggleVisibility': 'Show or hide password',
    'reset.submit': 'Save new password',
    'reset.submitting': 'Saving...',
    'reset.success': 'Password changed successfully. You can now sign in.',
    'reset.missingToken': 'Invalid recovery link. Request a new one from the sign-in page.',
    'reset.validation.minLength': 'The password must be at least 10 characters long.',
    'reset.validation.mismatch': 'The passwords do not match.',
    'reset.error.invalidToken': 'The recovery link is invalid or has expired. Request a new one.',
    'reset.error.generic': 'Could not change the password. Please try again.',
    'reset.backToLogin': 'Back to sign in',
  },
} as const;

export type TranslationKey = keyof typeof translations['pt-BR'];
