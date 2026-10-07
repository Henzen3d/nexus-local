/** Role no banco é `admin`. O pedido de UI também cita `ADMIN`. */
export function canShowRegisterUserButton(role: string | null | undefined): boolean {
  return (role ?? '').trim().toLowerCase() === 'admin'
}

export const REGISTER_USER_BUTTON_CLASS = 'register-user-btn'
