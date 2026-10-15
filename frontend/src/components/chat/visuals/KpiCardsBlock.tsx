import { VisualKpiCards } from './types';
import { formatVisualNumber } from './format';

interface Props {
  visual: VisualKpiCards;
}

export function KpiCardsBlock({ visual }: Props) {
  if (!visual.cards || visual.cards.length === 0) return null;

  const cols = Math.min(visual.cards.length, 3);
  const gridClass =
    cols === 1
      ? 'grid-cols-1'
      : cols === 2
      ? 'grid-cols-1 sm:grid-cols-2'
      : 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3';

  return (
    <div className={`grid gap-2.5 ${gridClass}`}>
      {visual.cards.map((card, idx) => (
        <div
          key={`${card.label}-${idx}`}
          className="bg-background rounded-lg p-4"
          style={{ border: '0.5px solid hsl(var(--border))' }}
        >
          <p className="text-[12px] text-muted-foreground mb-2">
            {card.label}
          </p>
          <p className="text-[20px] font-medium text-foreground tabular-nums leading-tight">
            {formatVisualNumber(card.value)}
          </p>
        </div>
      ))}
    </div>
  );
}
