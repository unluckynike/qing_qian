<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { assistantFeedback, streamAssistant, type ChatMessage } from '../api'
import { renderRichText } from '../utils/richtext'

interface Bubble {
  role: 'user' | 'assistant'
  content: string
  sources?: { doc: string; section: string }[]
  logId?: number | null
  voted?: 1 | -1
  voting?: boolean
}

const open = ref(false)
const input = ref('')
const sending = ref(false)
const bubbles = ref<Bubble[]>([])
const scrollEl = ref<HTMLElement | null>(null)

const suggestions = ['怎么求签?', 'AI 解签收费吗?', '为什么有些签没有卦象?', '忘记密码怎么办?']

function toggle() {
  open.value = !open.value
  if (open.value) scrollToBottom()
}

function scrollToBottom() {
  nextTick(() => {
    const el = scrollEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function send(text?: string) {
  const q = (text ?? input.value).trim()
  if (!q || sending.value) return
  input.value = ''
  bubbles.value.push({ role: 'user', content: q })
  bubbles.value.push({ role: 'assistant', content: '' })
  const idx = bubbles.value.length - 1
  sending.value = true
  scrollToBottom()

  const history: ChatMessage[] = bubbles.value
    .slice(0, -2)
    .slice(-4)
    .map((m) => ({ role: m.role, content: m.content.slice(0, 2000) }))

  try {
    await streamAssistant(
      { question: q, history },
      {
        onDelta: (t) => {
          bubbles.value[idx].content += t
          scrollToBottom()
        },
        onDone: (d) => {
          bubbles.value[idx].sources = d.sources
          bubbles.value[idx].logId = d.log_id ?? null
        },
        onError: (m) => {
          bubbles.value[idx].content += `\n(${m})`
        },
      },
    )
  } catch (e) {
    bubbles.value[idx].content += `\n(${e instanceof Error ? e.message : String(e)})`
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

/** 赞踩反馈(可改;失败静默,不打扰对话)。 */
async function vote(b: Bubble, v: 1 | -1) {
  if (!b.logId || b.voting || b.voted === v) return
  b.voting = true
  try {
    await assistantFeedback(b.logId, v)
    b.voted = v
  } catch {
    /* 静默 */
  } finally {
    b.voting = false
  }
}
</script>

<template>
  <div class="assistant-widget">
    <transition name="assistant-fade">
      <section v-if="open" class="assistant-panel">
        <header class="assistant-head">
          <span class="assistant-title">使用助手</span>
          <span class="assistant-sub">基于产品手册回答</span>
          <button class="assistant-close" aria-label="关闭" @click="open = false">×</button>
        </header>

        <div ref="scrollEl" class="assistant-body">
          <div v-if="!bubbles.length" class="assistant-welcome">
            <p style="margin: 0 0 10px">你好,我是青签的使用助手。使用上的问题都可以问我:</p>
            <div class="assistant-sugs">
              <button v-for="s in suggestions" :key="s" class="chip" @click="send(s)">{{ s }}</button>
            </div>
          </div>

          <div v-for="(m, i) in bubbles" :key="i" class="msg" :class="m.role">
            <div class="msg-label">{{ m.role === 'user' ? '我' : '助手' }}</div>
            <div
              class="msg-content"
              v-html="
                renderRichText(m.content) +
                (sending && i === bubbles.length - 1 ? '<span class=&quot;ai-caret&quot;>▍</span>' : '')
              "
            ></div>
            <div v-if="m.sources?.length" class="assistant-sources">
              参考:<span v-for="s in m.sources" :key="s.section">《{{ s.section }}》</span>
            </div>
            <div
              v-if="m.role === 'assistant' && m.logId && !(sending && i === bubbles.length - 1)"
              class="vote-row"
            >
              <button class="vote-btn" :class="{ active: m.voted === 1 }" title="答得好" @click="vote(m, 1)">👍</button>
              <button class="vote-btn" :class="{ active: m.voted === -1 }" title="答得不好" @click="vote(m, -1)">👎</button>
              <span v-if="m.voted" class="vote-thanks">已记录,谢谢反馈</span>
            </div>
          </div>
        </div>

        <div class="assistant-input">
          <input
            v-model="input"
            class="input"
            maxlength="200"
            placeholder="输入使用问题,回车发送…"
            @keyup.enter="send()"
          />
          <button class="btn small" :disabled="sending" @click="send()">发送</button>
        </div>
        <div class="assistant-foot">回答由 AI 基于产品手册生成,仅供参考</div>
      </section>
    </transition>

    <button class="assistant-fab" :title="open ? '收起助手' : '使用助手'" @click="toggle">
      {{ open ? '×' : '问' }}
    </button>
  </div>
</template>

<style scoped>
.assistant-widget { position: fixed; right: 22px; bottom: 22px; z-index: 60; }
.assistant-fab {
  width: 54px; height: 54px; border-radius: 50%;
  border: none; cursor: pointer;
  background: linear-gradient(180deg, var(--vermilion-2), var(--vermilion));
  color: #fdf6e8; font-family: var(--font-song); font-size: 21px;
  box-shadow: 0 8px 20px rgba(125, 31, 26, 0.35), inset 0 1px 0 rgba(255, 235, 200, 0.4);
  transition: transform 0.18s, box-shadow 0.18s;
}
.assistant-fab:hover { transform: translateY(-2px); box-shadow: 0 12px 26px rgba(125, 31, 26, 0.4); }

.assistant-panel {
  position: absolute; right: 0; bottom: 68px;
  width: min(368px, calc(100vw - 44px));
  height: min(520px, 68vh);
  display: flex; flex-direction: column;
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.assistant-head {
  display: flex; align-items: baseline; gap: 8px;
  padding: 12px 14px 10px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, #fdf8ec, var(--paper-2));
}
.assistant-title { font-family: var(--font-song); font-weight: 700; font-size: 16px; letter-spacing: 0.16em; color: var(--ink); }
.assistant-sub { font-size: 11.5px; color: var(--ink-3); letter-spacing: 0.08em; }
.assistant-close {
  margin-left: auto; border: none; background: none; cursor: pointer;
  font-size: 19px; line-height: 1; color: var(--ink-3); padding: 0 2px;
}
.assistant-close:hover { color: var(--vermilion); }

.assistant-body { flex: 1; overflow-y: auto; padding: 14px; }
.assistant-welcome { color: var(--ink-2); font-size: 14px; }
.assistant-sugs { display: flex; flex-wrap: wrap; gap: 8px; }
.assistant-sugs .chip { font-size: 13px; padding: 5px 12px; }

.assistant-sources { margin-top: 6px; font-size: 12px; color: var(--ink-3); }
.assistant-sources span { margin-right: 6px; }

.vote-row { display: flex; align-items: center; gap: 6px; margin-top: 8px; }
.vote-btn {
  appearance: none; cursor: pointer;
  border: 1px solid var(--line-2); background: var(--paper-2);
  border-radius: 8px; padding: 1px 9px; font-size: 13px; line-height: 1.7;
  opacity: 0.72; transition: all 0.15s;
}
.vote-btn:hover { opacity: 1; border-color: var(--vermilion); }
.vote-btn.active {
  opacity: 1; border-color: var(--vermilion);
  background: rgba(156, 43, 35, 0.09);
  box-shadow: 0 0 0 1px rgba(156, 43, 35, 0.25) inset;
}
.vote-thanks { font-size: 12px; color: var(--ink-3); }

.assistant-input {
  display: flex; gap: 8px; align-items: center;
  padding: 10px 12px; border-top: 1px solid var(--line);
}
.assistant-input .input { flex: 1; padding: 9px 12px; font-size: 14px; }
.assistant-foot {
  padding: 0 12px 10px; font-size: 11.5px; color: var(--ink-3); text-align: center;
}

.assistant-fade-enter-active, .assistant-fade-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.assistant-fade-enter-from, .assistant-fade-leave-to { opacity: 0; transform: translateY(10px); }

@media (max-width: 560px) {
  .assistant-widget { right: 14px; bottom: 14px; }
  .assistant-panel { height: min(60vh, 460px); }
}
</style>
