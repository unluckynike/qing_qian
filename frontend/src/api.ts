/** 后端 API 客户端:签文库 / 抽签 / SSE 流式解签 / 历史。 */

const BASE = '/api'

export interface SignBrief {
  no: number
  title: string
  ancient: string
  lucky?: string
}

export interface SignDetail extends SignBrief {
  summary: string
  poem: string[]
  jieyue: string
  hexagram: string
  overview: string
  image_url: string | null
  vernacular: { poem: string[]; jieyue: string }
  categories: Record<string, string>
  source_url: string
  lucky?: string
  lucky_tone?: string
}

export interface DrawResult {
  drawing_id: number | null
  sign: SignDetail
}

export interface HistoryItem {
  drawing_id: number
  sign_no: number
  title: string
  category: string | null
  question: string | null
  created_at: string | null
  reading_id: number | null
  excerpt: string | null
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface InterpretPayload {
  sign_no: number
  question?: string
  category?: string
  drawing_id?: number
  reading_id?: number
  history?: ChatMessage[]
}

export interface InterpretDone {
  done: true
  model?: string
  reading_id?: number
  drawing_id?: number
  message_id?: number
}

export interface AssistantDone {
  done: true
  mode?: string
  sources?: { doc: string; section: string }[]
  log_id?: number | null
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(BASE + url, init)
  if (!resp.ok) {
    let detail = `请求失败 (HTTP ${resp.status})`
    try {
      const data = await resp.json()
      if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* 非 JSON 响应 */
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

export function fetchSigns(): Promise<{ meta: Record<string, unknown>; signs: SignBrief[] }> {
  return request('/signs')
}

export function fetchSign(no: number): Promise<SignDetail> {
  return request(`/signs/${no}`)
}

export function drawSign(payload: { category?: string; question?: string }): Promise<DrawResult> {
  return request('/draw', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...userHeaders() },
    body: JSON.stringify(payload),
  })
}

export function fetchHistory(limit = 30): Promise<{ items: HistoryItem[] }> {
  return request(`/history?limit=${limit}`, { headers: userHeaders() })
}

/**
 * SSE 流式解签。onDelta 逐段回调,onDone 在服务端确认完成(含落库 id)后触发。
 */
export async function streamInterpret(
  payload: InterpretPayload,
  handlers: {
    onDelta: (text: string) => void
    onDone: (done: InterpretDone) => void
    onError: (message: string) => void
  },
  signal?: AbortSignal,
): Promise<void> {
  await postSSE(
    '/interpret',
    payload,
    {
      onDelta: handlers.onDelta,
      onDone: (d) => handlers.onDone(d as InterpretDone),
      onError: handlers.onError,
    },
    signal,
  )
}

/** 通用 SSE 消费器:`data: {...}` 帧解析(interpret 与 assistant 共用)。 */
async function postSSE(
  url: string,
  payload: unknown,
  handlers: {
    onDelta: (text: string) => void
    onDone: (done: unknown) => void
    onError: (message: string) => void
  },
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(BASE + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...userHeaders() },
    body: JSON.stringify(payload),
    signal,
  })
  if (!resp.ok) {
    let detail = `请求失败 (HTTP ${resp.status})`
    try {
      const data = await resp.json()
      if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* 忽略 */
    }
    throw new Error(detail)
  }
  if (!resp.body) {
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep: number
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      for (const line of block.split('\n')) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6)
        if (raw === '[DONE]') return
        let evt: Record<string, unknown>
        try {
          evt = JSON.parse(raw)
        } catch {
          continue
        }
        if (typeof evt.delta === 'string') handlers.onDelta(evt.delta)
        else if (typeof evt.error === 'string') {
          handlers.onError(evt.error)
          return
        } else if (evt.done) {
          handlers.onDone(evt)
        }
      }
    }
  }
}

/** 使用助手问答(SSE 流式;基于 docs/ 知识库)。 */
export async function streamAssistant(
  payload: { question: string; history?: ChatMessage[] },
  handlers: {
    onDelta: (text: string) => void
    onDone: (done: AssistantDone) => void
    onError: (message: string) => void
  },
  signal?: AbortSignal,
): Promise<void> {
  await postSSE(
    '/assistant/chat',
    payload,
    {
      onDelta: handlers.onDelta,
      onDone: (d) => handlers.onDone(d as AssistantDone),
      onError: handlers.onError,
    },
    signal,
  )
}

/** 把 AI 输出按 【小节】 拆块,供流式渲染。 */
export function parseAiSections(text: string): { title: string | null; body: string }[] {
  if (!text) return []
  const parts = text.split(/【([^】]{1,6})】/)
  const out: { title: string | null; body: string }[] = []
  if (parts[0]?.trim()) out.push({ title: null, body: parts[0].trim() })
  for (let i = 1; i < parts.length; i += 2) {
    out.push({ title: parts[i], body: (parts[i + 1] ?? '').trim() })
  }
  return out
}

/* ==================== 普通用户(注册/登录) ==================== */

export interface AuthUser {
  id: number
  username: string
  nickname: string
  created_at: string | null
}

export interface AuthLoginResult {
  role: 'user' | 'admin'
  token: string
  expires_at: number
  user?: AuthUser
}

const USER_TOKEN_KEY = 'qq_user_token'

export function getUserToken(): string {
  return localStorage.getItem(USER_TOKEN_KEY) ?? ''
}

export function setUserToken(token: string): void {
  if (token) localStorage.setItem(USER_TOKEN_KEY, token)
  else localStorage.removeItem(USER_TOKEN_KEY)
}

/** 所有需要"以当前用户身份"的请求都带上此头(未登录则为空)。 */
export function userHeaders(): Record<string, string> {
  const t = getUserToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export function authRegister(
  username: string,
  password: string,
  nickname?: string,
): Promise<AuthLoginResult> {
  return request('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, nickname: nickname || undefined }),
  })
}

export function authLogin(username: string, password: string): Promise<AuthLoginResult> {
  return request('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function authMe(): Promise<{ user: AuthUser }> {
  return request('/auth/me', { headers: userHeaders() })
}

/** 助手回答赞踩反馈(1=赞 / -1=踩;可改)。 */
export function assistantFeedback(logId: number, feedback: 1 | -1): Promise<{ ok: boolean; feedback: number }> {
  return request('/assistant/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...userHeaders() },
    body: JSON.stringify({ log_id: logId, feedback }),
  })
}

/* ==================== 后台管理 ==================== */

const ADMIN_TOKEN_KEY = 'qq_admin_token'
let adminToken = localStorage.getItem(ADMIN_TOKEN_KEY) ?? ''

export function getAdminToken(): string {
  return adminToken
}

export function setAdminToken(token: string): void {
  adminToken = token
  if (token) localStorage.setItem(ADMIN_TOKEN_KEY, token)
  else localStorage.removeItem(ADMIN_TOKEN_KEY)
}

export interface AdminOverview {
  drawings: number
  readings: number
  messages: number
  users: number
  drawings_today: number
  ai: { configured: boolean; model: string; api_base: string }
}

export interface AdminDrawing {
  drawing_id: number
  sign_no: number
  title: string
  category: string | null
  question: string | null
  created_at: string | null
  reading_id: number | null
  reading_model: string | null
  excerpt: string | null
  messages: number
}

export interface AdminUser {
  id: number
  username: string | null
  nickname: string | null
  is_active: boolean
  created_at: string | null
  drawings: number
  last_drawing_at: string | null
}

export interface LoginLogItem {
  id: number
  username: string
  role: 'user' | 'admin'
  action: string
  success: boolean
  reason: string | null
  ip: string | null
  user_agent: string | null
  created_at: string | null
}

export interface AssistantLogItem {
  id: number
  user: string
  question: string
  answer: string
  mode: string
  sources: { doc: string; section: string }[]
  feedback: number | null
  created_at: string | null
}

export interface AdminSettings {
  llm_api_base: string
  llm_model: string
  llm_temperature: number
  llm_max_tokens: number
  llm_thinking: string
  embedding_model: string
  llm_api_key_set: boolean
  llm_api_key_masked: string
}

export interface KbStatus {
  chunks: number
  embedded: number
  last_built_at: string | null
  files: string[]
  embedding_configured: boolean
}

async function adminRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(BASE + url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${adminToken}`,
      ...(init?.headers ?? {}),
    },
  })
  if (!resp.ok) {
    let detail = `请求失败 (HTTP ${resp.status})`
    try {
      const data = await resp.json()
      if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* 忽略 */
    }
    if (resp.status === 401 && !url.includes('/login')) {
      setAdminToken('')
      throw new Error('登录已过期,请重新登录')
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

export async function adminLogin(username: string, password: string): Promise<void> {
  const data = await request<{ token: string }>('/admin/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  setAdminToken(data.token)
}

export function adminOverview(): Promise<AdminOverview> {
  return adminRequest('/admin/overview')
}

export function adminDrawings(limit = 20, offset = 0): Promise<{ total: number; items: AdminDrawing[] }> {
  return adminRequest(`/admin/drawings?limit=${limit}&offset=${offset}`)
}

export function adminDeleteDrawing(id: number): Promise<{ ok: boolean }> {
  return adminRequest(`/admin/drawings/${id}`, { method: 'DELETE' })
}

export function adminUsers(q?: string): Promise<{ items: AdminUser[] }> {
  const suffix = q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''
  return adminRequest(`/admin/users${suffix}`)
}

export function adminResetUserPassword(id: number, password: string): Promise<{ ok: boolean }> {
  return adminRequest(`/admin/users/${id}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ password }),
  })
}

export function adminSetUserStatus(id: number, isActive: boolean): Promise<{ ok: boolean; is_active: boolean }> {
  return adminRequest(`/admin/users/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active: isActive }),
  })
}

export function adminDeleteUser(id: number): Promise<{ ok: boolean }> {
  return adminRequest(`/admin/users/${id}`, { method: 'DELETE' })
}

export function adminLoginLogs(
  limit = 50,
  offset = 0,
  onlyFailed = false,
): Promise<{ total: number; items: LoginLogItem[] }> {
  return adminRequest(`/admin/login-logs?limit=${limit}&offset=${offset}&only_failed=${onlyFailed}`)
}

export function adminGetSettings(): Promise<AdminSettings> {
  return adminRequest('/admin/settings')
}

export function adminUpdateSettings(values: Partial<Record<string, string | number>>): Promise<AdminSettings> {
  return adminRequest('/admin/settings', { method: 'PUT', body: JSON.stringify(values) })
}

export function adminTestLLM(): Promise<{ ok: boolean; model: string; latency_ms: number; reply: string }> {
  return adminRequest('/admin/settings/test', { method: 'POST' })
}

export function adminKbStatus(): Promise<KbStatus> {
  return adminRequest('/admin/kb/status')
}

export function adminKbRebuild(): Promise<{ mode: string; chunks: number; embedding_error: string | null }> {
  return adminRequest('/admin/kb/rebuild', { method: 'POST' })
}

export function adminAssistantLogs(
  limit = 50,
  offset = 0,
  onlyBad = false,
): Promise<{ total: number; stats: { up: number; down: number; unrated: number }; items: AssistantLogItem[] }> {
  return adminRequest(`/admin/assistant-logs?limit=${limit}&offset=${offset}&only_bad=${onlyBad}`)
}
