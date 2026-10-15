import { VisualDetailTable, VisualDetailTableColumn } from './types';
import { formatVisualNumber } from './format';

interface Props {
  visual: VisualDetailTable;
}

const norm = (s: string) => s.toLowerCase();

// Apenas colunas explicitamente monetárias devem receber formatação de valor
const MONETARY_KEY_RE =
  /^(result_value|line_total|valor|value|amount|total|saldo|aberto|open_amount|open_value|net_value|gross_value|line_value|line_amount|item_value|item_amount|preco|price)$/;

const isMonetaryColumn = (col: VisualDetailTableColumn): boolean => {
  if (col.format === 'currency') return true;
  const k = norm(col.key);
  return MONETARY_KEY_RE.test(k);
};

const isDateColumn = (col: VisualDetailTableColumn): boolean => {
  const k = norm(col.key);
  const l = norm(col.label || '');
  return /(date|data|venc|due|emiss|dt_)/.test(k) || /(data|vencimento|emiss)/.test(l);
};

export const formatMoney = (v: number, currency = 'BRL'): string => {
  try {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
    }).format(v);
  } catch {
    // Código de moeda inválido: número com 2 casas, sem símbolo.
    return new Intl.NumberFormat('pt-BR', {
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
    }).format(v);
  }
};

// Renderiza o valor respeitando o tipo da coluna.
// Datas e textos: valor original (a API já envia datas formatadas em dd/mm/yyyy).
// Numéricos não monetários: inteiros sem casas, decimais com 2 casas (formatVisualNumber).
// Monetários: na moeda do modelo, com 2 casas decimais ("R$ 10.834,00").
const formatCell = (
  col: VisualDetailTableColumn | undefined,
  v: unknown,
  currency?: string,
): string => {
  if (v === null || v === undefined || v === '') return '—';
  if (col && isDateColumn(col)) return String(v);
  if (typeof v === 'number') {
    if (col && isMonetaryColumn(col)) return formatMoney(v, currency);
    return formatVisualNumber(v);
  }
  return String(v);
};

const isNumeric = (v: unknown): v is number => typeof v === 'number';

// Heurística: identificar papéis dos campos com base no key/label
const classifyColumns = (columns: VisualDetailTableColumn[]) => {
  const findCol = (matchers: RegExp[]) =>
    columns.find((c) => matchers.some((m) => m.test(norm(c.key)) || m.test(norm(c.label))));

  const primary =
    findCol([/document|doc|codigo|código|code|number|numero|número|id$/]) ?? columns[0];

  const secondary =
    findCol([/type|tipo|categoria|category|class/]) ??
    columns.find((c) => c.key !== primary?.key);

  const date =
    findCol([/date|data|venc|due|emiss/]) ??
    columns.find((c) => c.key !== primary?.key && c.key !== secondary?.key);

  // Apenas considera coluna de valor se for explicitamente monetária — nada de fallback.
  const amount = columns.find((c) => isMonetaryColumn(c));

  const usedKeys = new Set(
    [primary, secondary, date, amount].filter(Boolean).map((c) => c!.key)
  );
  const extras = columns.filter((c) => !usedKeys.has(c.key));

  return { primary, secondary, date, amount, extras };
};

export function DetailTableBlock({ visual }: Props) {
  if (
    !Array.isArray(visual.columns) ||
    visual.columns.length === 0 ||
    !Array.isArray(visual.data) ||
    visual.data.length === 0
  ) {
    return null;
  }

  const { primary, secondary, date, amount, extras } = classifyColumns(visual.columns);
  const currency = visual.currency || 'BRL';

  const total = visual.row_count ?? visual.data.length;
  const showing = visual.data.length;

  return (
    <div className="w-full space-y-2">
      {visual.data.map((row, idx) => {
        const primaryVal = primary ? row[primary.key] : undefined;
        const secondaryVal = secondary ? row[secondary.key] : undefined;
        const dateVal = date ? row[date.key] : undefined;
        const amountVal = amount ? row[amount.key] : undefined;

        return (
          <div
            key={idx}
            className="rounded-lg bg-background px-4 py-3 transition-colors"
            style={{ border: '0.5px solid hsl(var(--border))' }}
          >
            <div className="flex items-start justify-between gap-4">
              {/* Left: identity */}
              <div className="min-w-0 flex-1">
                {primary && (
                  <p className="text-[14px] font-medium text-foreground truncate">
                    {formatCell(primary, primaryVal, currency)}
                  </p>
                )}
                {secondary && secondaryVal !== primaryVal && (
                  <p className="text-[13px] text-muted-foreground mt-0.5 truncate">
                    {formatCell(secondary, secondaryVal, currency)}
                  </p>
                )}
                {date && (
                  <p className="text-[12px] text-muted-foreground/80 mt-1.5">
                    <span className="text-muted-foreground/60">{date.label}: </span>
                    <span className="text-foreground/80 tabular-nums">
                      {formatCell(date, dateVal, currency)}
                    </span>
                  </p>
                )}
              </div>

              {/* Right: amount highlight */}
              {amount && (
                <div className="text-right shrink-0">
                  <p className="text-[12px] text-muted-foreground/70">
                    {amount.label}
                  </p>
                  <p
                    className={`text-[14px] font-medium mt-0.5 tabular-nums ${
                      isNumeric(amountVal) ? 'text-foreground' : 'text-foreground/80'
                    }`}
                  >
                    {formatCell(amount, amountVal, currency)}
                  </p>
                </div>
              )}
            </div>

            {/* Extra fields, if any — discreet metadata row */}
            {extras.length > 0 && (
              <div className="mt-2 pt-2 flex flex-wrap gap-x-4 gap-y-1" style={{ borderTop: '0.5px solid hsl(var(--border))' }}>
                {extras.map((col) => {
                  const v = row[col.key];
                  if (v === null || v === undefined || v === '') return null;
                  return (
                    <p key={col.key} className="text-[12px] text-muted-foreground">
                      <span className="text-muted-foreground/60">{col.label}: </span>
                      <span
                        className={`text-foreground/80 ${
                          isNumeric(v) ? 'tabular-nums' : ''
                        }`}
                      >
                        {formatCell(col, v, currency)}
                      </span>
                    </p>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}

      {total > showing && (
        <p className="text-[12px] text-muted-foreground/60 pl-1 pt-1">
          Mostrando {showing} de {total} registros
        </p>
      )}
    </div>
  );
}
