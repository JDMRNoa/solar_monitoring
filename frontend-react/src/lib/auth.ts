import Cookies from 'js-cookie'

const TOKEN_KEY = 'solarmonitor_jwt'
const ROLE_KEY = 'solarmonitor_role'

export function setToken(token: string, role: string) {
  // Guardar por 7 días
  Cookies.set(TOKEN_KEY, token, { expires: 7 })
  Cookies.set(ROLE_KEY, role, { expires: 7 })
}

export function removeToken() {
  Cookies.remove(TOKEN_KEY)
  Cookies.remove(ROLE_KEY)
}

export function getToken(): string | undefined {
  return Cookies.get(TOKEN_KEY)
}

export function getRole(): string | undefined {
  return Cookies.get(ROLE_KEY)
}

export function isAuthenticated(): boolean {
  return !!getToken()
}
