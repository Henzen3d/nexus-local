import React, { ButtonHTMLAttributes } from 'react'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg' | 'icon'
  isLoading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
  /** Explicit custom tooltip (preferred). Falls back to `title` if omitted. */
  tooltip?: string
  /** Where the custom tooltip opens. Default: down. Use `up` near the bottom of the screen. */
  tooltipPlacement?: 'up' | 'down'
}

/**
 * Design-system button.
 * Any `title` / `tooltip` is rendered with the app's custom tooltip pattern
 * (`custom-tooltip-trigger` + `data-tooltip`) so native browser balloons are not used.
 */
export function Button({
  className = '',
  variant = 'secondary',
  size = 'md',
  isLoading = false,
  leftIcon,
  rightIcon,
  children,
  disabled,
  tooltip,
  tooltipPlacement = 'down',
  title,
  ...props
}: ButtonProps) {
  const tipText =
    (typeof tooltip === 'string' && tooltip.trim() ? tooltip : undefined) ??
    (typeof title === 'string' && title.trim() ? title : undefined)
  const hasTip = Boolean(tipText)

  const finalClassName = [
    'btn',
    `btn-${variant}`,
    `btn-${size}`,
    isLoading ? 'btn-loading' : '',
    hasTip ? 'custom-tooltip-trigger' : '',
    hasTip && tooltipPlacement === 'up' ? 'tooltip-up' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      className={finalClassName}
      disabled={disabled || isLoading}
      data-tooltip={hasTip ? tipText : undefined}
      // Suppress native tooltip to avoid double balloons
      title={undefined}
      {...props}
    >
      {leftIcon && <span className="btn-icon-slot btn-icon-left">{leftIcon}</span>}
      {children}
      {rightIcon && <span className="btn-icon-slot btn-icon-right">{rightIcon}</span>}
    </button>
  )
}
