/**
 * Formatação numérica partilhada pelos widgets de visuais (KPI, charts, tabela).
 *
 * Regra: valores inteiros renderizam sem casas decimais ("10.834"); valores com
 * parte decimal mantêm 2 casas ("6,63"). Strings (valores já formatados pelo
 * backend) e números não-finitos passam intactos.
 *
 * Nota: só trata de casas decimais e agrupamento — não há qualquer lógica de
 * percentagem/×100 aqui (essa assimetria é do backend).
 */
export function formatVisualNumber(value: number | string): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return String(value);
  return new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value);
}
