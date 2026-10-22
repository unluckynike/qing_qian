<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { gsap } from 'gsap'
import { drawSign } from '../api'

const router = useRouter()
const question = ref('')
const category = ref('')
const rolling = ref(false)
const error = ref('')
const categories = ['事业', '姻缘', '财运', '健康', '其他']

// 示例问题:选中分类后联动输入框示例,未选时轮播。
// 示例纪律(见 docs):一事一签、单一主题、带时间范围、口语化。
const CATEGORY_EXAMPLES: Record<string, string> = {
  事业: '例:今年该不该换工作?',
  姻缘: '例:我和 TA 的缘分如何?',
  财运: '例:今年下半年的财运走势如何?',
  健康: '例:我今年的身体要注意些什么?',
  其他: '例:这件事接下来会如何发展?',
}
const GENERAL_EXAMPLES = [
  '例:今年下半年的财运如何?',
  '例:这份工作要不要接?',
  '例:我和 TA 的缘分如何?',
]
const exampleIdx = ref(0)
let exampleTimer: number | undefined

const questionPlaceholder = computed(() => {
  if (category.value) return CATEGORY_EXAMPLES[category.value] ?? GENERAL_EXAMPLES[0]
  return GENERAL_EXAMPLES[exampleIdx.value % GENERAL_EXAMPLES.length]
})

const pageEl = ref<HTMLElement | null>(null)
const stageEl = ref<HTMLElement | null>(null)
let ctx: gsap.Context | undefined
let watchdog: number | undefined

function reducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

const ANIMATED = [
  '.hero-mark', '.hero-title', '.hero-sub', '.hero-line',
  '.draw-stage', '.steps > *', '.ritual-form > *', '.quick-card',
].join(',')

/** 兜底:标签页被节流时 rAF 驱动的时间线可能迟迟不完成,
 *  到点强制清除 GSAP 内联样式,保证内容始终可见。 */
function ensureVisible() {
  if (!pageEl.value) return
  gsap.set(pageEl.value.querySelectorAll(ANIMATED), {
    clearProps: 'transform,opacity,visibility,translate,rotate,scale',
  })
}

/* ---------- 摇签仪式:慢起 → 转急 → 停顿 → 落签 ----------
 *  仪式总时长每次随机(2.2–3.6s),但抽签结果早已由服务端定下——
 *  时长只影响观感,不影响随机性。转场由 startDraw 的定时器推进,
 *  动画被节流也不阻塞落签。 */
const RITUAL_MIN = 2.2
const RITUAL_MAX = 3.6

let ritualTl: gsap.core.Timeline | undefined
let tubeTween: gsap.core.Tween | undefined
let stickTween: gsap.core.Tween | undefined

function clearRitual() {
  ritualTl?.kill()
  tubeTween?.kill()
  stickTween?.kill()
  ritualTl = tubeTween = stickTween = undefined
}

/** 复位签筒:清掉摇签留下的内联样式(落签签回到隐藏态)。 */
function resetStage() {
  clearRitual()
  if (!stageEl.value) return
  gsap.set(stageEl.value.querySelectorAll('.tube, .stick, .drawn-stick'), {
    clearProps: 'transform,opacity',
  })
}

function playRitual(total: number) {
  if (!stageEl.value) return
  const tube = stageEl.value.querySelector('.tube')
  const sticks = stageEl.value.querySelectorAll('.stick')
  const drawn = stageEl.value.querySelector('.drawn-stick')
  if (!tube || !drawn) return

  gsap.set(tube, { rotation: 0 })
  gsap.set(sticks, { y: 0 })
  gsap.set(drawn, { opacity: 0, y: 60 })

  if (reducedMotion()) {
    // 不做摇动,短暂停顿后直接亮出落签结果
    ritualTl = gsap.timeline()
    ritualTl.set(drawn, { opacity: 1, y: -46 }, 0.25)
    return
  }

  const emergeAt = Math.max(1.2, total - 0.85) // 落签前留 0.85s 展示
  const slowSpan = emergeAt * 0.45
  const fastSpan = emergeAt * 0.38
  const pauseAt = slowSpan + fastSpan

  const shake = (amp: number, speed: number, jitter: number) => () => {
    tubeTween?.kill()
    stickTween?.kill()
    tubeTween = gsap.fromTo(
      tube,
      { rotation: -amp },
      { rotation: amp, duration: speed, yoyo: true, repeat: -1, ease: 'sine.inOut' },
    )
    stickTween = gsap.fromTo(
      sticks,
      { y: 0 },
      {
        y: -jitter, duration: speed * 0.8, yoyo: true, repeat: -1,
        ease: 'sine.inOut', stagger: { each: 0.035, from: 'center' },
      },
    )
  }

  const tl = gsap.timeline()
  tl.call(shake(2.2, 0.26, 3.5), [], 0) // 慢起:小幅轻摇
  tl.call(shake(5, 0.15, 8), [], slowSpan) // 转急:幅度与签条跳动加大
  tl.call(() => {
    tubeTween?.kill()
    stickTween?.kill()
  }, [], pauseAt)
  tl.to(tube, { rotation: 0, duration: 0.26, ease: 'sine.out' }, pauseAt + 0.02) // 停顿回正
  tl.to(sticks, { y: 0, duration: 0.22, ease: 'sine.out' }, pauseAt + 0.02)
  tl.to(drawn, { opacity: 1, y: -46, duration: 0.72, ease: 'power2.out' }, emergeAt) // 落签
  ritualTl = tl
}

onMounted(() => {
  exampleTimer = window.setInterval(() => {
    exampleIdx.value = (exampleIdx.value + 1) % GENERAL_EXAMPLES.length
  }, 5000)
  if (!pageEl.value || reducedMotion()) return
  ctx = gsap.context(() => {
    // 入场时间线:标题落定 → 签筒登场 → 步骤/表单/快捷入口错峰浮现
    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
    tl.from('.hero-mark', { autoAlpha: 0, y: -10, duration: 0.5 })
      .from('.hero-title', { autoAlpha: 0, y: 18, duration: 0.7 }, '-=0.25')
      .from('.hero-sub', { autoAlpha: 0, duration: 0.5 }, '-=0.35')
      .from('.hero-line', { autoAlpha: 0, scaleX: 0.4, duration: 0.5 }, '-=0.25')
      .from('.draw-stage', { autoAlpha: 0, y: 26, scale: 0.96, duration: 0.7 }, '-=0.2')
      .from('.steps > *', { autoAlpha: 0, y: 8, duration: 0.4, stagger: 0.06 }, '-=0.35')
      .from('.ritual-form > *', { autoAlpha: 0, y: 12, duration: 0.45, stagger: 0.09 }, '-=0.25')
      .from('.quick-card', { autoAlpha: 0, y: 14, duration: 0.5, stagger: 0.1 }, '-=0.2')
    // 签筒持续轻度呼吸
    gsap.to('.tube', { y: -7, duration: 1.9, yoyo: true, repeat: -1, ease: 'sine.inOut', delay: 1.3 })
  }, pageEl.value)
  watchdog = window.setTimeout(ensureVisible, 4000)
})
onUnmounted(() => {
  window.clearTimeout(watchdog)
  window.clearInterval(exampleTimer)
  clearRitual()
  ctx?.revert()
})

async function startDraw() {
  if (rolling.value) return
  error.value = ''
  rolling.value = true
  resetStage()
  const total = reducedMotion() ? 0.9 : RITUAL_MIN + Math.random() * (RITUAL_MAX - RITUAL_MIN)
  const started = Date.now()
  playRitual(total)
  try {
    const result = await drawSign({
      category: category.value || undefined,
      question: question.value.trim() || undefined,
    })
    // 仪式(含落签展示)走完再转场;若请求慢于动画,拿到结果后尽快转场
    const remain = Math.max(150, total * 1000 - (Date.now() - started))
    window.setTimeout(() => {
      const query: Record<string, string> = { fresh: '1' }
      if (result.drawing_id) query.drawing_id = String(result.drawing_id)
      if (question.value.trim()) query.question = question.value.trim()
      if (category.value) query.category = category.value
      router.push({ path: `/sign/${result.sign.no}`, query })
    }, remain)
  } catch (e) {
    resetStage()
    rolling.value = false
    error.value = e instanceof Error ? e.message : String(e)
  }
}
</script>

<template>
  <div ref="pageEl" class="home">
    <header class="hero center">
      <div class="hero-mark">☯</div>
      <h1 class="hero-title">青签</h1>
      <p class="hero-sub">吕祖灵签 · 心诚则灵</p>
      <div class="hero-line"></div>
    </header>

    <!-- 求签仪式区:签筒为主角,默念/摇签/落签一气呵成 -->
    <section class="ritual">
      <div ref="stageEl" class="draw-stage">
        <div class="tube">
          <div class="tube-sticks">
            <i v-for="n in 7" :key="n" class="stick"></i>
          </div>
          <div class="tube-body">
            <span class="tube-title">吕祖灵签</span>
            <span class="tube-ring"></span>
          </div>
          <div class="drawn-stick"></div>
        </div>
      </div>

      <ul class="steps">
        <li class="step"><span class="step-num">一</span>诚心默念</li>
        <li class="step-sep"></li>
        <li class="step"><span class="step-num">二</span>摇动签筒</li>
        <li class="step-sep"></li>
        <li class="step"><span class="step-num">三</span>落签求解</li>
      </ul>

      <p class="muted ritual-hint">
        {{ rolling ? '签筒摇动中,静候落签……' : '心诚则灵,一事一签' }}
      </p>

      <div class="ritual-form">
        <input
          v-model="question"
          class="input"
          maxlength="100"
          :placeholder="questionPlaceholder"
          :disabled="rolling"
        />
        <div class="chips center-chips">
          <button
            v-for="c in categories"
            :key="c"
            type="button"
            class="chip"
            :class="{ active: category === c }"
            :aria-pressed="category === c"
            @click="category = category === c ? '' : c"
          >{{ c }}</button>
        </div>
        <button class="btn btn-draw" :disabled="rolling" @click="startDraw">
          {{ rolling ? '摇 签 中' : '摇 签' }}
        </button>
        <div class="field-hint hint-line">
          <span>所问之事 · 选填,默念亦可</span>
          <span>{{ question.length }}/100</span>
        </div>
      </div>

      <div v-if="error" class="banner error" style="width: 100%">{{ error }}</div>
    </section>

    <!-- 快捷入口 -->
    <div class="quick-links">
      <router-link to="/library" class="quick-card">
        <div class="quick-title">签文库</div>
        <div class="quick-desc">吕祖灵签 · 一百签全集</div>
        <span class="quick-arrow">→</span>
      </router-link>
      <router-link to="/history" class="quick-card">
        <div class="quick-title">签事记</div>
        <div class="quick-desc">我的抽签与解签记录</div>
        <span class="quick-arrow">→</span>
      </router-link>
    </div>
  </div>
</template>

<style scoped>
.home { max-width: 720px; margin: 0 auto; }

.hero { padding: 6px 0 0; }
.hero-mark { font-size: 26px; color: var(--gold); line-height: 1; }
.hero-title {
  font-family: var(--font-song);
  font-size: clamp(40px, 9vw, 58px);
  font-weight: 700;
  letter-spacing: 0.22em;
  text-indent: 0.22em;
  margin: 8px 0 6px;
}
.hero-sub { color: var(--ink-2); letter-spacing: 0.42em; text-indent: 0.42em; font-size: 14.5px; margin: 0; }
.hero-line {
  width: 120px; height: 2px; margin: 18px auto 0;
  background: linear-gradient(90deg, transparent, var(--gold-2), transparent);
  position: relative;
}
.hero-line::after {
  content: ""; position: absolute; left: 50%; top: -2.5px;
  width: 7px; height: 7px; background: var(--gold); transform: translateX(-50%) rotate(45deg);
}

.ritual {
  margin-top: 16px;
  padding: 24px 22px 22px;
  border-radius: var(--radius);
  border: 1px solid var(--line);
  background:
    radial-gradient(420px 200px at 50% 0%, rgba(168, 128, 58, 0.09), transparent 70%),
    linear-gradient(180deg, rgba(253, 248, 236, 0.92), rgba(250, 245, 233, 0.55));
  box-shadow: var(--shadow-sm);
  display: flex; flex-direction: column; align-items: center;
}

.steps {
  list-style: none; display: flex; align-items: center; justify-content: center;
  gap: 12px; margin: 16px 0 0; padding: 0; flex-wrap: wrap;
  color: var(--ink-3); font-size: 13px; letter-spacing: 0.14em;
}
.step { display: flex; align-items: center; gap: 6px; }
.step-num {
  width: 20px; height: 20px; flex: none;
  border: 1px solid var(--gold-2); border-radius: 50%;
  display: grid; place-items: center;
  font-family: var(--font-song); font-size: 11.5px; color: var(--gold-ink);
}
.step-sep { width: 26px; height: 1px; background: var(--line-2); }

.ritual-hint { margin: 14px 0 12px; letter-spacing: 0.1em; }

.ritual-form { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.ritual-form .input { max-width: 460px; text-align: center; }
.hint-line { width: 100%; max-width: 460px; }
.center-chips { justify-content: center; }
.btn-draw { width: min(260px, 100%); padding: 14px 0; font-size: 17px; }

.quick-links { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 18px; }
.quick-card {
  position: relative;
  padding: 16px 18px;
  border: 1px solid var(--line); border-radius: 12px;
  background: var(--paper-2);
  text-decoration: none; color: var(--ink);
  transition: transform 0.18s, box-shadow 0.18s, border-color 0.18s;
}
.quick-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-sm); border-color: var(--gold-2); }
.quick-title { font-family: var(--font-song); font-weight: 700; font-size: 16.5px; letter-spacing: 0.16em; }
.quick-desc { color: var(--ink-3); font-size: 13px; margin-top: 4px; }
.quick-arrow {
  position: absolute; right: 16px; top: 50%;
  transform: translateY(-50%);
  color: var(--gold-ink); font-size: 17px;
  transition: transform 0.18s;
}
.quick-card:hover .quick-arrow { transform: translateY(-50%) translateX(3px); }

@media (max-width: 560px) {
  .quick-links { grid-template-columns: 1fr; }
}
</style>
