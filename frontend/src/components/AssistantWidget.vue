<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { gsap } from 'gsap'
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

const rootEl = ref<HTMLElement | null>(null)
let ctx: gsap.Context | undefined
let hintTimer: number | undefined
let hintHideTimer: number | undefined

const HINT_KEY = 'qq_assistant_hint_seen'

const open = ref(false)
const showHint = ref(false)
const input = ref('')
const sending = ref(false)
const bubbles = ref<Bubble[]>([])
const scrollEl = ref<HTMLElement | null>(null)

const suggestions = ['怎么求签?', '求签有什么讲究?', 'AI 解签收费吗?', '忘记密码怎么办?']

onMounted(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!reduced && rootEl.value) {
    ctx = gsap.context(() => {
      // 入场:弹性落位;随后进入持续呼吸浮动
      gsap.from('.assistant-fab', {
        autoAlpha: 0,
        y: 18,
        scale: 0.7,
        duration: 0.6,
        ease: 'back.out(1.8)',
        delay: 1.1,
      })
      gsap.to('.fab-mascot', { y: -2.5, duration: 1.6, yoyo: true, repeat: -1, ease: 'sine.inOut', delay: 1.8 })
    }, rootEl.value)
  }
  // 兜底:若渲染节流导致入场未完成,3.5 秒后强制可见(与全站策略一致)
  window.setTimeout(() => {
    if (rootEl.value) {
      gsap.set(rootEl.value.querySelectorAll('.assistant-fab'), {
        clearProps: 'transform,opacity,visibility,translate,rotate,scale',
      })
    }
  }, 3500)

  // 首次访问:一次性引导气泡(消除"这是解签吗"的歧义)
  if (!localStorage.getItem(HINT_KEY)) {
    hintTimer = window.setTimeout(() => {
      showHint.value = true
      localStorage.setItem(HINT_KEY, '1')
      hintHideTimer = window.setTimeout(() => (showHint.value = false), 9000)
    }, 1800)
  }
})
onUnmounted(() => {
  window.clearTimeout(hintTimer)
  window.clearTimeout(hintHideTimer)
  ctx?.revert()
})

function toggle() {
  open.value = !open.value
  if (open.value) {
    showHint.value = false
    scrollToBottom()
  }
}

function dismissHint() {
  showHint.value = false
  window.clearTimeout(hintHideTimer)
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
  <div ref="rootEl" class="assistant-widget">
    <!-- 首次引导气泡:说明"我是谁、我能干什么" -->
    <transition name="assistant-fade">
      <div v-if="showHint && !open" class="assistant-hint">
        <button class="hint-close" aria-label="关闭提示" @click.stop="dismissHint">×</button>
        <p>你好,我是<strong>青小签</strong>~<br />使用上的问题,可以问我哦</p>
      </div>
    </transition>

    <transition name="assistant-fade">
      <section v-if="open" class="assistant-panel">
        <header class="assistant-head">
          <span class="head-mascot" aria-hidden="true">
            <svg viewBox="0 0 64 64">
              <path d="M18 50 L32 64 L46 50" fill="none" stroke="#9c2b23" stroke-width="3.4" stroke-linejoin="round" />
              <circle cx="32" cy="11" r="5.5" fill="#2b2b2b" />
              <rect x="26.5" y="15" width="11" height="2.6" rx="1.3" fill="#b58a3d" />
              <circle cx="32" cy="34.5" r="17" fill="#fdf8ec" stroke="#2b2b2b" stroke-width="2" />
              <path d="M23.5 34 q3.5 -4 7 0" fill="none" stroke="#2b2b2b" stroke-width="2.2" stroke-linecap="round" />
              <path d="M33.5 34 q3.5 -4 7 0" fill="none" stroke="#2b2b2b" stroke-width="2.2" stroke-linecap="round" />
              <circle cx="22" cy="40" r="2.8" fill="#b8402f" opacity="0.5" />
              <circle cx="42" cy="40" r="2.8" fill="#b8402f" opacity="0.5" />
              <path d="M28.5 41.5 q3.5 3 7 0" fill="none" stroke="#2b2b2b" stroke-width="2" stroke-linecap="round" />
            </svg>
          </span>
          <span class="assistant-title">青小签</span>
          <span class="assistant-sub">使用助手 · 基于站内文档</span>
          <button class="assistant-close" aria-label="关闭" @click="open = false">×</button>
        </header>

        <div ref="scrollEl" class="assistant-body">
          <div v-if="!bubbles.length" class="assistant-welcome">
            <p style="margin: 0 0 10px">你好,我是青小签——青签的使用助手。使用上的问题,或想了解吕祖与吕祖灵签的文化背景,都可以问我:</p>
            <div class="assistant-sugs">
              <button v-for="s in suggestions" :key="s" class="chip" @click="send(s)">{{ s }}</button>
            </div>
          </div>

          <div v-for="(m, i) in bubbles" :key="i" class="msg" :class="m.role">
            <div class="msg-label">{{ m.role === 'user' ? '我' : '青小签' }}</div>
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
        <div class="assistant-foot">回答由 AI 基于站内文档生成,仅供参考</div>
      </section>
    </transition>

    <!-- 形象化悬浮按钮:青小签(药丸形,文字明确语义) -->
    <button class="assistant-fab" :class="{ open }" :title="open ? '收起助手' : '使用助手 · 青小签'" @click="toggle">
      <span class="fab-mascot" aria-hidden="true">
        <svg v-if="!open" viewBox="0 0 64 64">
          <path d="M18 50 L32 64 L46 50" fill="none" stroke="#9c2b23" stroke-width="3.4" stroke-linejoin="round" />
          <circle cx="32" cy="11" r="5.5" fill="#2b2b2b" />
          <rect x="26.5" y="15" width="11" height="2.6" rx="1.3" fill="#b58a3d" />
          <circle cx="32" cy="34.5" r="17" fill="#fdf8ec" stroke="#2b2b2b" stroke-width="2" />
          <path d="M23.5 34 q3.5 -4 7 0" fill="none" stroke="#2b2b2b" stroke-width="2.2" stroke-linecap="round" />
          <path d="M33.5 34 q3.5 -4 7 0" fill="none" stroke="#2b2b2b" stroke-width="2.2" stroke-linecap="round" />
          <circle cx="22" cy="40" r="2.8" fill="#b8402f" opacity="0.5" />
          <circle cx="42" cy="40" r="2.8" fill="#b8402f" opacity="0.5" />
          <path d="M28.5 41.5 q3.5 3 7 0" fill="none" stroke="#2b2b2b" stroke-width="2" stroke-linecap="round" />
        </svg>
        <span v-else class="fab-close">×</span>
      </span>
      <span class="fab-text">
        <b>{{ open ? '收起' : '青小签' }}</b>
        <i>{{ open ? '关闭对话' : '使用助手' }}</i>
      </span>
    </button>
  </div>
</template>

<style scoped>
.assistant-widget { position: fixed; right: 22px; bottom: 22px; z-index: 60; display: flex; flex-direction: column; align-items: flex-end; }

/* ---------- 悬浮按钮(药丸) ---------- */
.assistant-fab {
  display: flex; align-items: center; gap: 9px;
  padding: 7px 16px 7px 8px;
  border: 1px solid var(--line-3); border-radius: 999px;
  background: linear-gradient(180deg, #fdf8ec, var(--paper-2));
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(74, 50, 22, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.7);
  transition: transform 0.18s, box-shadow 0.18s, border-color 0.18s;
}
.assistant-fab:hover {
  transform: translateY(-2px) rotate(-1.5deg);
  box-shadow: 0 14px 30px rgba(74, 50, 22, 0.24);
  border-color: var(--gold-2);
}
.assistant-fab.open { padding-right: 14px; }
.fab-mascot {
  width: 40px; height: 40px; flex: none;
  border-radius: 50%;
  background: radial-gradient(120% 120% at 50% 18%, #fffdf6, #f3ead6);
  border: 1.5px solid rgba(156, 43, 35, 0.35);
  display: grid; place-items: center;
  box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.6);
}
.fab-mascot svg { width: 33px; height: 33px; margin-top: 1px; }
.fab-close { font-size: 22px; line-height: 1; color: var(--vermilion); }
.fab-text { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.25; }
.fab-text b { font-family: var(--font-song); font-size: 15px; letter-spacing: 0.14em; color: var(--ink); }
.fab-text i { font-style: normal; font-size: 11px; letter-spacing: 0.18em; color: var(--ink-3); }
@media (max-width: 560px) {
  .assistant-fab { padding: 6px; }
  .fab-text { display: none; }
}

/* ---------- 首次引导气泡 ---------- */
.assistant-hint {
  position: relative; margin-bottom: 10px; margin-right: 6px;
  background: var(--paper-2); border: 1px solid var(--line);
  border-radius: 12px; padding: 10px 14px;
  box-shadow: var(--shadow);
  font-size: 13.5px; color: var(--ink); line-height: 1.7;
  animation: hint-in 0.45s cubic-bezier(0.2, 0.9, 0.3, 1.2);
}
.assistant-hint strong { color: var(--vermilion); font-family: var(--font-song); letter-spacing: 0.08em; }
.assistant-hint::after {
  content: ""; position: absolute; right: 34px; bottom: -7px;
  width: 12px; height: 12px; background: var(--paper-2);
  border-right: 1px solid var(--line); border-bottom: 1px solid var(--line);
  transform: rotate(45deg);
}
.hint-close {
  position: absolute; top: 4px; right: 6px;
  border: none; background: none; cursor: pointer;
  font-size: 15px; line-height: 1; color: var(--ink-3);
}
.hint-close:hover { color: var(--vermilion); }
@keyframes hint-in { from { opacity: 0; transform: translateY(8px) scale(0.94); } to { opacity: 1; transform: none; } }

/* ---------- 对话面板 ---------- */
.assistant-panel {
  width: min(368px, calc(100vw - 44px));
  height: min(520px, 68vh);
  margin-bottom: 12px;
  display: flex; flex-direction: column;
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: var(--shadow);
  overflow: hidden;
  transform-origin: bottom right;
}
.assistant-head {
  display: flex; align-items: center; gap: 8px;
  padding: 11px 14px 10px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, #fdf8ec, var(--paper-2));
}
.head-mascot {
  width: 30px; height: 30px; flex: none;
  border-radius: 50%;
  background: radial-gradient(120% 120% at 50% 18%, #fffdf6, #f3ead6);
  border: 1px solid rgba(156, 43, 35, 0.3);
  display: grid; place-items: center;
}
.head-mascot svg { width: 25px; height: 25px; margin-top: 1px; }
.assistant-title { font-family: var(--font-song); font-weight: 700; font-size: 16px; letter-spacing: 0.16em; color: var(--ink); }
.assistant-sub { font-size: 11.5px; color: var(--ink-3); letter-spacing: 0.06em; }
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
  border: 1px solid var(--line-3); background: var(--paper-2);
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

@media (prefers-reduced-motion: reduce) {
  .assistant-hint { animation: none; }
}
@media (max-width: 560px) {
  .assistant-widget { right: 14px; bottom: 14px; }
  .assistant-panel { height: min(60vh, 460px); }
}
</style>
