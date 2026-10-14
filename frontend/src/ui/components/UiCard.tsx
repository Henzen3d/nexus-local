import React, { forwardRef } from 'react'

/**
 * Casca comum dos cartões do Intelligent UI (plano 11, "camada visual").
 *
 * Modelada no par Card + CardHeader do OpenUI (Thesys, MIT), reescrita com os tokens
 * do Multi+: cabeçalho com ícone, título, subtítulo e ações à direita; corpo; rodapé.
 * Todo o estilo mora em `index.css` (classes `nexus-ui-card*`), nada inline, para o
 * tema claro/escuro, `prefers-reduced-motion` e `:fullscreen` valerem para todos.
 */

type CardElement = 'div' | 'section' | 'form' | 'figure'

export interface UiCardProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  /** Elemento raiz. `form` para o ControlsCard, `figure` para o sandbox. */
  as?: CardElement
  /** Ícone pequeno antes do título (lucide, 16 px). */
  icon?: React.ReactNode
  title?: React.ReactNode
  /** Linha secundária sob o título. */
  subtitle?: React.ReactNode
  /** Conteúdo à direita do título: métrica, chip, botões. */
  actions?: React.ReactNode
  /** Rodapé separado por linha fina (legenda, botão de envio, erro). */
  footer?: React.ReactNode
  /**
   * `card`: corpo com padding (padrão). `flush`: corpo sem padding, para iframe e
   * conteúdo que encosta na borda.
   */
  variant?: 'card' | 'flush'
  /** `id` do título, para `aria-labelledby` em formulários. */
  titleId?: string
  children?: React.ReactNode
}

export const UiCard = forwardRef<HTMLElement, UiCardProps>(function UiCard(
  {
    as = 'section',
    icon,
    title,
    subtitle,
    actions,
    footer,
    variant = 'card',
    titleId,
    className,
    children,
    ...rest
  },
  ref
) {
  const Root = as as React.ElementType
  const hasHeader = Boolean(title || subtitle || actions || icon)
  const classes = ['nexus-ui-card', className].filter(Boolean).join(' ')

  return (
    <Root ref={ref} className={classes} data-variant={variant} {...rest}>
      {hasHeader && (
        <header className="nexus-ui-card__header">
          <div className="nexus-ui-card__heading">
            {icon && (
              <span className="nexus-ui-card__icon" aria-hidden="true">
                {icon}
              </span>
            )}
            <div className="nexus-ui-card__titles">
              {title && (
                <h4 id={titleId} className="nexus-ui-card__title">
                  {title}
                </h4>
              )}
              {subtitle && <p className="nexus-ui-card__subtitle">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="nexus-ui-card__actions">{actions}</div>}
        </header>
      )}
      <div className="nexus-ui-card__body">{children}</div>
      {footer && <footer className="nexus-ui-card__footer">{footer}</footer>}
    </Root>
  )
})

/** Botão pequeno de ação do cabeçalho (ícone + rótulo), 44×44 mínimo no toque (spec §7). */
export function UiCardAction({
  icon,
  label,
  onClick,
  pressedLabel,
  pressed = false,
  disabled = false,
  hideLabel = false,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
  /** Texto temporário após a ação ("Copiado"). */
  pressedLabel?: string
  pressed?: boolean
  disabled?: boolean
  /** Só ícone visível; o rótulo fica para leitores de tela e no `title`. */
  hideLabel?: boolean
}) {
  const text = pressed && pressedLabel ? pressedLabel : label
  return (
    <button
      type="button"
      className="nexus-ui-action"
      onClick={onClick}
      disabled={disabled}
      title={text}
      aria-label={hideLabel ? text : undefined}
      aria-pressed={pressedLabel ? pressed : undefined}
      data-icon-only={hideLabel || undefined}
    >
      <span className="nexus-ui-action__icon" aria-hidden="true">
        {icon}
      </span>
      {!hideLabel && <span className="nexus-ui-action__label">{text}</span>}
    </button>
  )
}

export default UiCard
