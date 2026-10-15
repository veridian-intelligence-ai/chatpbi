import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart3, TrendingUp, GitBranch, LineChart } from 'lucide-react';

const ANALYSIS_CONFIG: Record<string, { label: string; icon: React.ElementType }> = {
  time_series: { label: 'Série Temporal', icon: LineChart },
  pareto: { label: 'Análise de Pareto', icon: BarChart3 },
  drivers: { label: 'Drivers de Variação', icon: GitBranch },
  forecast: { label: 'Previsão', icon: TrendingUp },
};

interface AnalyticsCardProps {
  analysisType: string;
  analytics: Record<string, unknown>;
}

export function AnalyticsCard({ analysisType, analytics }: AnalyticsCardProps) {
  const config = ANALYSIS_CONFIG[analysisType];
  if (!config) return null;

  const Icon = config.icon;

  return (
    <Card className="mt-2 border-border/60 bg-muted/30 shadow-sm">
      <CardHeader className="pb-2 pt-3 px-4">
        <CardTitle className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          <Icon className="w-3.5 h-3.5" />
          {config.label}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3">
        <pre className="text-[11px] leading-relaxed text-foreground/80 whitespace-pre-wrap break-words font-mono bg-background/50 rounded-lg p-3 max-h-64 overflow-auto">
          {JSON.stringify(analytics, null, 2)}
        </pre>
      </CardContent>
    </Card>
  );
}
