/** 普通用户会话(轻量响应式 store;令牌存 localStorage)。 */
import { reactive } from 'vue'
import { authMe, getAdminToken, getUserToken, setUserToken, type AuthUser } from '../api'

export const auth = reactive<{
  token: string
  user: AuthUser | null
  isAdmin: boolean
  ready: boolean
}>({
  token: getUserToken(),
  user: null,
  isAdmin: Boolean(getAdminToken()),
  ready: false,
})

export function setUserSession(token: string, user: AuthUser): void {
  auth.token = token
  auth.user = user
  setUserToken(token)
}

export function clearUserSession(): void {
  auth.token = ''
  auth.user = null
  setUserToken('')
}

/** 启动/刷新时用令牌换回用户信息;失败则清除(过期/非法)。 */
export async function refreshMe(): Promise<void> {
  if (!auth.token) {
    auth.ready = true
    return
  }
  try {
    const data = await authMe()
    auth.user = data.user
  } catch {
    clearUserSession()
  } finally {
    auth.ready = true
  }
}

/** 管理端登录/退出后同步"管理"入口显隐。 */
export function refreshAdminFlag(): void {
  auth.isAdmin = Boolean(getAdminToken())
}
