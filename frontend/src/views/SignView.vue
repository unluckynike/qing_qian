<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { gsap } from 'gsap'
import {
  fetchSign,
  parseAiSections,
  streamInterpret,
  type ChatMessage,
  type SignDetail,
} from '../api'

const route = useRoute()
const router = useRouter()

const pageEl = ref<HTMLElement | null>(null)
let ctx: gsap.Context | undefined
let watchdog: number | undefined

const sign = ref<SignDetail | null>(null)
const loadError = ref('')
const llmReady = ref<boolean | null>(null)

const no = computed(() => Number(route.params.no))
const fresh = computed(() => route.query.fresh === '1')
const fromQuestion = computed(() => String(route.query.question ?? ''))
const fromCategory = computed(() => String(route.query.category ?? ''))
const drawingId = computed(() => {
  const v = Number(route.query.drawing_id)
  return Number.isFinite(v) && v > 0 ? v : undefined
})

function reducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** 入场微动画:签牌上浮 → 签诗逐行 → 印章落章 → 面板错峰。 */
function animateIn() {
  ctx?.revert()
  if (!pageEl.value || reducedMotion()) return
  ctx = gsap.context(() => {
    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
    tl.from('.sign-plaque', { autoAlpha: 0, y: 22, duration: 0.55 })
      .from('.poem-line', { autoAlpha: 0, x: -14, duration: 0.45, stagger: 0.12 }, '-=0.22')
      .from(
        '.poem-seal',
        { autoAlpha: 0, scale: 2, rotate: -30, duration: 0.5, ease: 'back.out(2)' },
        '-=0.18',
      )
      .from(
        '.sign-page .grid-2 > .panel, .sign-page > .panel',
        { autoAlpha: 0, y: 16, duration: 0.5, stagger: 0.07 },
        '-=0.28',
      )
      .from('.sign-page .row-between', { autoAlpha: 0, duration: 0.4 }, '-=0.12')
  }, pageEl.value)
  // 兜底:标签页被节流时保证内容可见(与首页同一策略)
  window.clearTimeout(watchdog)
  watchdog = window.setTimeout(() => {
    if (!pageEl.value) return
    gsap.set(
      pageEl.value.querySelectorAll(
        '.sign-plaque, .poem-line, .poem-seal, .sign-page .grid-2 > .panel, .sign-page > .panel, .sign-page .row-between',
      ),
      { clearProps: 'transform,opacity,visibility,translate,rotate,scale' },
    )
  }, 4000)
}

async function load() {
  sign.value = null
  loadError.value = ''
  try {
    sign.value = await fetchSign(no.value)
    await nextTick()
    animateIn()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  }
}
watch(no, load, { immediate: true })
onUnmounted(() => {
  window.clearTimeout(watchdog)
  ctx?.revert()
})

onMounted(async () => {
  try {
    const resp = await fetch('/api/health')
    const data = await resp.json()
    llmReady.value = Boolean(data.llm_configured)
  } catch {
    llmReady.value = null
  }
})

// ---------- AI 解签 ----------
const aiState = ref<'idle' | 'streaming' | 'done' | 'error'>('idle')
const aiText = ref('')
const aiError = ref('')
const askQuestion = ref(fromQuestion.value)
const readingId = ref<number | undefined>()
const scrollBox = ref<HTMLElement | null>(null)

const aiBlocks = computed(() => parseAiSections(aiText.value))
const catList = computed(() => Object.entries(sign.value?.categories ?? {}))

/** 基调徽章配色:上上/上吉→朱金;中吉/中平→墨金;中下/下下→青灰 */
const luckyClass = computed(() => {
  const l = sign.value?.lucky || ''
  if (l.startsWith('上')) return 'lv-shang'
  if (l.startsWith('中下') || l.startsWith('下')) return 'lv-xia'
  return 'lv-zhong'
})

async function startInterpret() {
  if (!sign.value || aiState.value === 'streaming') return
  aiState.value = 'streaming'
  aiText.value = ''
  aiError.value = ''
  try {
    await streamInterpret(
      {
        sign_no: sign.value.no,
        question: askQuestion.value.trim() || undefined,
        category: fromCategory.value || undefined,
        drawing_id: drawingId.value,
      },
      {
        onDelta: (t) => {
          aiText.value += t
          scrollToBottom()
        },
        onDone: (d) => {
          readingId.value = d.reading_id
          aiState.value = 'done'
          rememberFirstAnswer()
        },
        onError: (m) => {
          aiError.value = m
          aiState.value = 'error'
        },
      },
    )
    if (aiState.value === 'streaming') {
      aiState.value = 'done'
      rememberFirstAnswer()
    }
  } catch (e) {
    aiError.value = e instanceof Error ? e.message : String(e)
    aiState.value = 'error'
  }
}

function rememberFirstAnswer() {
  if (thread.value.length === 0 && aiText.value.trim()) {
    thread.value.push({ role: 'assistant', content: aiText.value })
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = scrollBox.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// ---------- 追问 ----------
const thread = ref<ChatMessage[]>([])
const followup = ref('')
const sending = ref(false)

async function sendFollowup() {
  const q = followup.value.trim()
  if (!q || !sign.value || sending.value) return
  sending.value = true
  const history = thread.value
    .slice(-6)
    .map((m) => ({ role: m.role, content: m.content.slice(0, 2000) }))
  thread.value.push({ role: 'user', content: q })
  thread.value.push({ role: 'assistant', content: '' })
  const idx = thread.value.length - 1
  followup.value = ''
  scrollToBottom()
  try {
    await streamInterpret(
      { sign_no: sign.value.no, question: q, reading_id: readingId.value, history },
      {
        onDelta: (t) => {
          thread.value[idx].content += t
          scrollToBottom()
        },
        onDone: () => {},
        onError: (m) => {
          thread.value[idx].content += `\n(解签中断:${m})`
        },
      },
    )
  } catch (e) {
    thread.value[idx].content += `\n(解签失败:${e instanceof Error ? e.message : String(e)})`
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div v-if="loadError" class="banner error">{{ loadError }}</div>
  <div v-else-if="!sign" class="center muted" style="padding: 60px 0">签文加载中……</div>

  <div v-else ref="pageEl" class="stack-24 sign-page">
    <div v-if="fresh" class="banner info">
      已为君落签 —— 此签为方才摇得<span v-if="fromQuestion">,所问:「{{ fromQuestion }}」</span>
    </div>

    <!-- 签牌(紧凑版:横向签诗) -->
    <section class="sign-plaque">
      <div class="plaque-head">
        <span class="plaque-no">吕祖灵签</span>
        <h1 class="plaque-title">{{ sign.title }}</h1>
        <span v-if="sign.lucky" class="lucky-badge" :class="luckyClass" :title="sign.lucky_tone || ''">{{ sign.lucky }}</span>
        <span v-if="sign.ancient" class="plaque-ancient">典故 · {{ sign.ancient }}</span>
      </div>
      <div class="poem-frame">
        <div class="poem-horizontal">
          <div v-for="(line, i) in sign.poem" :key="i" class="poem-line">{{ line }}</div>
        </div>
        <span class="poem-seal">青<br />签<br />印</span>
      </div>
    </section>

    <!-- 双栏:古文解 / 白话详解 -->
    <div class="grid-2">
      <section class="panel">
        <div class="sec-title">解 曰</div>
        <p class="classic-text" style="margin: 0">{{ sign.jieyue || '(源本缺此项)' }}</p>
        <div class="sec-title" style="margin-top: 18px">卦 象</div>
        <p class="classic-text" style="margin: 0">{{ sign.hexagram || '(此签源本缺卦象)' }}</p>
        <template v-if="sign.overview">
          <div class="sec-title" style="margin-top: 18px">签 意 总 述</div>
          <p class="plain-text" style="margin: 0">{{ sign.overview }}</p>
        </template>
      </section>

      <section class="panel">
        <div class="sec-title">白 话 详 解</div>
        <p v-if="sign.vernacular.poem.length" class="classic-text" style="margin: 0">
          {{ sign.vernacular.poem.join('') }}
        </p>
        <p v-if="sign.vernacular.jieyue" class="plain-text" style="margin: 12px 0 0">
          {{ sign.vernacular.jieyue }}
        </p>
        <p v-if="sign.summary" class="plain-text" style="margin: 12px 0 0">{{ sign.summary }}</p>
        <p
          v-if="!sign.vernacular.poem.length && !sign.vernacular.jieyue && !sign.summary"
          class="muted"
          style="margin: 0"
        >
          (此签源本无白话详解段)
        </p>
      </section>
    </div>

    <!-- 分项释义 -->
    <section v-if="catList.length" class="panel">
      <div class="sec-title">传 统 分 项 释 义</div>
      <div class="cat-grid">
        <div v-for="[k, v] in catList" :key="k" class="cat-item">
          <div class="cat-key">{{ k }}</div>
          <div class="cat-val">{{ v }}</div>
        </div>
      </div>
    </section>

    <!-- AI 解签 -->
    <section class="panel ai-panel">
      <div class="sec-title">师 傅 解 签</div>

      <div v-if="llmReady === false" class="banner warm">
        AI 解签尚未配置:可在
        <router-link to="/admin">后台管理 → AI 配置</router-link>
        中填写 API Key(或改 backend/.env)—— 未配置不影响上方签文阅读。
      </div>

      <div v-if="aiState === 'idle'">
        <div class="ask-row">
          <input
            v-model="askQuestion"
            class="input"
            maxlength="100"
            placeholder="所问何事?(选填,如:今年事业如何)"
          />
          <button class="btn" :disabled="llmReady === false" @click="startInterpret">请 师 傅 解 签</button>
        </div>
        <p class="muted" style="margin-top: 8px">解签由 AI 依本签签文生成,仅供文化娱乐参考。</p>
      </div>

      <div v-else>
        <div ref="scrollBox" class="ai-scroll">
          <div class="ai-blocks">
            <div v-for="(b, i) in aiBlocks" :key="i" class="ai-block">
              <div v-if="b.title" class="ai-block-title">{{ b.title }}</div>
              <div class="ai-block-body">{{ b.body }}</div>
            </div>
            <span v-if="aiState === 'streaming'" class="ai-caret">▍</span>
          </div>

          <div v-if="thread.length > 1" class="followup-thread">
            <div v-for="(m, i) in thread.slice(1)" :key="i" class="msg" :class="m.role">
              <div class="msg-label">{{ m.role === 'user' ? '问' : '答' }}</div>
              <div class="msg-content">{{ m.content }}</div>
            </div>
          </div>
        </div>

        <div v-if="aiError" class="banner error">{{ aiError }}</div>

        <div v-if="aiState === 'done'" class="followup">
          <div class="ask-row">
            <input
              v-model="followup"
              class="input"
              maxlength="100"
              placeholder="还有何疑问,可继续问师傅……"
              @keyup.enter="sendFollowup"
            />
            <button class="btn ghost" :disabled="sending" @click="sendFollowup">
              {{ sending ? '求解中…' : '追 问' }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- 底部动作 -->
    <div class="row-between">
      <router-link to="/library" class="muted" style="text-decoration: none">← 回签文库</router-link>
      <button class="btn ghost" @click="router.push('/')">再 抽 一 签</button>
    </div>
  </div>
</template>

<style scoped>
.sign-page { --panel-gap: 20px; }
.ai-scroll {
  max-height: 46vh;
  overflow-y: auto;
  padding-right: 6px;
  margin-top: 4px;
}
.followup-thread {
  margin-top: 16px;
  border-top: 1px dashed var(--line-2);
  padding-top: 8px;
}
</style>
