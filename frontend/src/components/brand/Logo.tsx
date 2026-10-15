import { APP_NAME } from '@/config/app';

interface LogoProps {
  className?: string;
}

/**
 * Símbolo do app: um balão de conversa com três barras, desenhado em linha,
 * que herda a cor do texto (`currentColor`). A cor vem do `className` do pai
 * (por exemplo, `text-primary`). Para usar a logo da empresa, troque este
 * componente e os ícones de `public/`.
 */
export function Logo({ className }: LogoProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label={APP_NAME}
      className={className}
    >
      <path d="M4 4.5h16a1.5 1.5 0 0 1 1.5 1.5v10a1.5 1.5 0 0 1-1.5 1.5h-8.5L7 21v-3.5H4A1.5 1.5 0 0 1 2.5 16V6A1.5 1.5 0 0 1 4 4.5z" />
      <path d="M8 13.5v-1.5M12 13.5V9.5M16 13.5V8" />
    </svg>
  );
}
