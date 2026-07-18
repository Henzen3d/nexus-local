import type { SVGProps } from 'react'

/**
 * Ícone "Buy me a coffee" (xícara + saquinho).
 * Usa currentColor para acompanhar a cor do texto adjacente.
 * Referência: buy-a-coffee.jpeg / buy-a-coffee.svg (export vazio — recriado).
 */
export function BuyCoffeeIcon({
  size = 16,
  className,
  ...props
}: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
      {...props}
    >
      {/* Corpo da xícara */}
      <path d="M4.5 8.5h11.5v7.2c0 1.7-1.4 3.1-3.1 3.1H7.6c-1.7 0-3.1-1.4-3.1-3.1V8.5z" />
      {/* Alça */}
      <path d="M16 9.5h1.2c1.5 0 2.7 1.2 2.7 2.7s-1.2 2.7-2.7 2.7H16" />
      {/* Pratinho */}
      <path d="M5 20.5h10" />
      {/* Saquinho de chá */}
      <path d="M10.2 8.5V5.8" />
      <path d="M10.2 5.8c0-.9.6-1.5 1.4-1.5.7 0 1.2.5 1.2 1.2 0 .9-.8 1.3-1.4 1.8l-1.2 1" />
      <rect x="8.6" y="10.2" width="3.2" height="3.6" rx="0.6" fill="currentColor" stroke="none" />
    </svg>
  )
}
