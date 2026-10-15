import { VeridianVisual } from './types';
import { KpiCardsBlock } from './KpiCardsBlock';
import { BarChartBlock } from './BarChartBlock';
import { LineChartBlock } from './LineChartBlock';
import { DetailTableBlock } from './DetailTableBlock';

interface Props {
  visual?: VeridianVisual | null;
}

export function VeridianVisualRenderer({ visual }: Props) {
  if (!visual || typeof visual !== 'object' || !('visual_type' in visual)) return null;

  let body: JSX.Element | null = null;

  if (visual.visual_type === 'kpi_cards') {
    if (!Array.isArray(visual.cards) || visual.cards.length === 0) return null;
    body = <KpiCardsBlock visual={visual} />;
  } else if (visual.visual_type === 'chart') {
    if (
      !visual.x_field ||
      !visual.y_field ||
      !Array.isArray(visual.data) ||
      visual.data.length === 0
    ) {
      return null;
    }
    if (visual.chart_type === 'bar') body = <BarChartBlock visual={visual} />;
    else if (visual.chart_type === 'line') body = <LineChartBlock visual={visual} />;
    else return null;
  } else if (visual.visual_type === 'detail_table') {
    if (
      !Array.isArray(visual.columns) ||
      visual.columns.length === 0 ||
      !Array.isArray(visual.data) ||
      visual.data.length === 0
    ) {
      return null;
    }
    body = <DetailTableBlock visual={visual} />;
  } else {
    return null;
  }

  if (!body) return null;

  // KPI cards são naturalmente "cards", não precisam do wrapper extra
  const isKpi = visual.visual_type === 'kpi_cards';

  return (
    <div className="mt-3 animate-fade-in">
      {visual.title && !isKpi && (
        <p className="text-[12px] text-muted-foreground mb-2 pl-0.5">
          {visual.title}
        </p>
      )}
      {isKpi ? (
        body
      ) : (
        <div className="bg-background rounded-lg p-3" style={{ border: '0.5px solid hsl(var(--border))' }}>
          {body}
        </div>
      )}
    </div>
  );
}
