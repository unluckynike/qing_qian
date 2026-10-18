<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  fetchSign,
  parseAiSections,
  streamInterpret,
  type ChatMessage,
  type SignDetail,
} from '../api'

const route = useRoute()
const router = useRouter()

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

async function load() {
  sign.value = null
  loadError.value = ''
  try {
    sign.value = await fetchSign(no.value)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  }
}
watch(no, load, { immediate: true })

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

// 竖排签诗高度 = 最长句字数 × (1em 字宽 + 0.32em 字距) + 余量。
// 必须给足高度,否则 WebView 会按容器高度把竖排文字折列,渲染成错位多列。
const poemHeightStyle = computed(() => {
  const lines = sign.value?.poem ?? []
  const maxChars = Math.max(1, ...lines.map((l) => l.length))
  return { height: `${(maxChars * 1.32 + 0.8).toFixed(2)}em` }
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
const thread = ref<ChatMessage[]>([]) // [0]=首答,其后为追问问答(仅作上下文,渲染用 slice(1))
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

  <div v-else class="stack-24">
    <div v-if="fresh" class="banner info reveal">
      已为君落签 —— 此签为方才摇得<span v-if="fromQuestion">,所问:「{{ fromQuestion }}」</span>
    </div>

    <!-- 签牌 -->
    <div class="sign-plaque reveal">
      <div class="plaque-head">
        <span class="plaque-no">吕祖灵签</span>
        <h1 class="plaque-title">{{ sign.title }}</h1>
      </div>
      <div class="poem-frame">
        <div class="poem-vertical" :style="poemHeightStyle">
          <div v-for="(line, i) in sign.poem" :key="i" class="poem-line">{{ line }}</div>
        </div>
        <span class="poem-seal">青<br />签<br />印</span>
      </div>
      <div class="plaque-caption">— 签 诗 —</div>
    </div>

    <!-- 古文解 -->
    <div class="panel reveal d1">
      <div class="sec-title">解 曰</div>
      <p class="classic-text" style="margin: 0">{{ sign.jieyue || '(源本缺此项)' }}</p>
      <div class="sec-title" style="margin-top: 24px">卦 象</div>
      <p class="classic-text" style="margin: 0">{{ sign.hexagram || '(此签源本缺卦象)' }}</p>
      <template v-if="sign.overview">
        <div class="sec-title" style="margin-top: 24px">签 意 总 述</div>
        <p class="plain-text" style="margin: 0">{{ sign.overview }}</p>
      </template>
    </div>

    <!-- 白话详解 -->
    <div class="panel reveal d2">
      <div class="sec-title">白 话 详 解</div>
      <p v-if="sign.vernacular.poem.length" class="classic-text" style="margin: 0">
        {{ sign.vernacular.poem.join('') }}
      </p>
      <p v-if="sign.vernacular.jieyue" class="plain-text" style="margin: 14px 0 0">
        {{ sign.vernacular.jieyue }}
      </p>
      <p v-if="sign.summary" class="plain-text" style="margin: 14px 0 0">{{ sign.summary }}</p>
      <p
        v-if="!sign.vernacular.poem.length && !sign.vernacular.jieyue && !sign.summary"
        class="muted"
        style="margin: 0"
      >
        (此签源本无白话详解段)
      </p>
    </div>

    <!-- 分项释义 -->
    <div v-if="catList.length" class="panel reveal d3">
      <div class="sec-title">传 统 分 项 释 义</div>
      <div class="cat-grid">
        <div v-for="[k, v] in catList" :key="k" class="cat-item">
          <div class="cat-key">{{ k }}</div>
          <div class="cat-val">{{ v }}</div>
        </div>
      </div>
    </div>

    <!-- AI 解签 -->
    <div class="panel ai-panel reveal d4">
      <div class="sec-title">师 傅 解 签</div>

      <div v-if="llmReady === false" class="banner warm">
        AI 解签尚未配置:在 <code>backend/.env</code> 中填写 <code>LLM_API_KEY</code> 后即可使用
        —— 未配置不影响上方签文阅读。
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
        <p class="muted" style="margin-top: 10px">解签由 AI 依本签签文生成,仅供文化娱乐参考。</p>
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
    </div>

    <!-- 底部动作 -->
    <div class="row-between reveal d4">
      <router-link to="/library" class="muted" style="text-decoration: none">← 回签文库</router-link>
      <button class="btn ghost" @click="router.push('/')">再 抽 一 签</button>
    </div>
  </div>
</template>

<style scoped>
.ai-scroll {
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 6px;
  margin-top: 4px;
}
.followup-thread {
  margin-top: 18px;
  border-top: 1px dashed var(--line-2);
  padding-top: 8px;
}
</style>
