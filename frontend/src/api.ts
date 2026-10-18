/** 后端 API 客户端:签文库 / 抽签 / SSE 流式解签 / 历史。 */

const BASE = '/api'

export interface SignBrief {
  no: number
  title: string
  ancient: string
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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchHistory(limit = 30): Promise<{ items: HistoryItem[] }> {
  return request(`/history?limit=${limit}`)
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
  const resp = await fetch(BASE + '/interpret', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
          handlers.onDone(evt as unknown as InterpretDone)
        }
      }
    }
  }
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
