export interface VisualKpiCard {
  label: string;
  value: number | string;
}

export interface VisualKpiCards {
  visual_type: 'kpi_cards';
  title?: string;
  cards: VisualKpiCard[];
  /** Código ISO 4217 da moeda do modelo (ex.: "BRL"). */
  currency?: string;
}

export interface VisualChart {
  visual_type: 'chart';
  chart_type: 'bar' | 'line';
  title?: string;
  x_field: string;
  y_field: string;
  x_label?: string;
  y_label?: string;
  data: Array<Record<string, string | number>>;
  currency?: string;
}

export interface VisualDetailTableColumn {
  key: string;
  label: string;
  /** "currency" quando a coluna é um valor em dinheiro (marcado pelo backend). */
  format?: 'currency';
}

export interface VisualDetailTable {
  visual_type: 'detail_table';
  title?: string;
  columns: VisualDetailTableColumn[];
  data: Array<Record<string, string | number | null | undefined>>;
  row_count?: number;
  currency?: string;
}

export type VeridianVisual = VisualKpiCards | VisualChart | VisualDetailTable;
