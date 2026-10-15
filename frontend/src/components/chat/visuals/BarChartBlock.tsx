import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { VisualChart } from './types';
import { formatVisualNumber } from './format';

interface Props {
  visual: VisualChart;
}

const truncate = (s: string, n = 14) =>
  s.length > n ? s.slice(0, n - 1) + '…' : s;

export function BarChartBlock({ visual }: Props) {
  if (!visual.data || visual.data.length === 0) return null;

  const longestLabel = Math.max(
    ...visual.data.map((d) => String(d[visual.x_field] ?? '').length)
  );
  const needsRotate = longestLabel > 8 || visual.data.length > 5;

  return (
    <div className="w-full h-[260px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={visual.data}
          margin={{ top: 8, right: 8, left: 0, bottom: needsRotate ? 36 : 8 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="hsl(var(--border))"
            vertical={false}
          />
          <XAxis
            dataKey={visual.x_field}
            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
            tickLine={false}
            axisLine={{ stroke: 'hsl(var(--border))' }}
            angle={needsRotate ? -25 : 0}
            textAnchor={needsRotate ? 'end' : 'middle'}
            height={needsRotate ? 50 : 24}
            interval={0}
            tickFormatter={(v) => truncate(String(v))}
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) =>
              typeof v === 'number' ? new Intl.NumberFormat('pt-BR', { notation: 'compact' }).format(v) : v
            }
          />
          <Tooltip
            cursor={{ fill: 'hsl(var(--accent))', opacity: 0.4 }}
            contentStyle={{
              background: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: '0.75rem',
              fontSize: '12px',
              boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
            }}
            labelStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }}
            formatter={(value: number | string) => [formatVisualNumber(value), visual.y_label || visual.y_field]}
          />
          <Bar
            dataKey={visual.y_field}
            fill="hsl(var(--primary))"
            radius={[6, 6, 0, 0]}
            maxBarSize={48}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
