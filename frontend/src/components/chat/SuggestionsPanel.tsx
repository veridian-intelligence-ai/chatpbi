import { Sparkles, ArrowUpRight, Database, Shield, ChevronDown, Wifi } from 'lucide-react';
import { useState } from 'react';

const defaultSuggestions = [
  'Quanto paguei neste ano?',
  'Quanto tenho a receber em aberto?',
  'Faça uma análise de pareto do contas a receber liquidado de 2025',
  'Compare o ano vigente com o mesmo periodo do ultimo ano?',
];

interface SuggestionsPanelProps {
  onSendQuery: (query: string) => void;
  variant?: 'sidebar' | 'inline';
  dynamicSuggestions?: string[];
}

function SessionStatus() {
  return (
    <div className="rounded-xl bg-accent/60 p-3.5">
      <p className="text-[9px] font-bold text-muted-foreground/60 tracking-[0.15em] uppercase mb-3">Sessão analítica</p>
      <div className="space-y-2.5">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-primary/8 flex items-center justify-center">
            <Database className="h-3 w-3 text-primary" />
          </div>
          <div>
            <p className="text-[11px] font-semibold text-foreground leading-none">Power BI</p>
            <p className="text-[9px] text-muted-foreground mt-0.5">Modelo semântico</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-primary/8 flex items-center justify-center">
            <Shield className="h-3 w-3 text-primary" />
          </div>
          <div>
            <p className="text-[11px] font-semibold text-foreground leading-none">Conexão segura</p>
            <p className="text-[9px] text-muted-foreground mt-0.5">HTTPS · Sessão ativa</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-primary/8 flex items-center justify-center">
            <Wifi className="h-3 w-3 text-primary" />
          </div>
          <div className="flex items-center gap-1.5">
            <p className="text-[11px] font-semibold text-foreground leading-none">Status</p>
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-primary/10 text-[9px] font-semibold text-primary">
              <span className="w-1 h-1 rounded-full bg-primary status-pulse" />
              Conectado
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function PanelContent({ onSendQuery, dynamicSuggestions }: { onSendQuery: (query: string) => void; dynamicSuggestions?: string[] }) {
  const hasDynamic = dynamicSuggestions && dynamicSuggestions.length > 0;
  const suggestions = hasDynamic ? dynamicSuggestions : defaultSuggestions;
  const label = hasDynamic ? 'Próximos passos sugeridos' : 'Pergunte agora';

  return (
    <div className="space-y-4">
      <SessionStatus />

      {/* Suggestions */}
      <div>
        <div className="flex items-center gap-1.5 mb-2 px-1">
          <Sparkles className="h-3 w-3 text-primary" />
          <p className="text-[9px] font-bold text-muted-foreground/60 tracking-[0.15em] uppercase">{label}</p>
        </div>
        <div className="space-y-px">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => onSendQuery(s)}
              className="group w-full flex items-center justify-between text-left text-[11px] text-muted-foreground hover:text-foreground px-3 py-2 rounded-lg hover:bg-accent/80 transition-all duration-150"
            >
              <span className="leading-snug">{s}</span>
              <ArrowUpRight className="h-3 w-3 shrink-0 opacity-0 group-hover:opacity-100 text-primary transition-opacity duration-150" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function SuggestionsPanel({ onSendQuery, variant = 'sidebar', dynamicSuggestions }: SuggestionsPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (variant === 'inline') {
    return (
      <div className="border-t border-border bg-card/60">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full flex items-center justify-between px-4 py-2.5 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors"
        >
          <span>Contexto & Sugestões</span>
          <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
        </button>
        {isExpanded && (
          <div className="px-4 pb-3 animate-fade-in">
            <PanelContent onSendQuery={onSendQuery} dynamicSuggestions={dynamicSuggestions} />
          </div>
        )}
      </div>
    );
  }

  return (
    <aside className="w-[264px] border-l border-border bg-card h-full overflow-y-auto shrink-0 hidden xl:block">
      <div className="p-4">
        <PanelContent onSendQuery={onSendQuery} dynamicSuggestions={dynamicSuggestions} />
      </div>
    </aside>
  );
}
