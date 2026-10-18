<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { gsap } from 'gsap'
import { drawSign } from '../api'

const router = useRouter()
const question = ref('')
const category = ref('')
const rolling = ref(false)
const error = ref('')
const categories = ['事业', '姻缘', '财运', '健康', '其他']

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

onMounted(() => {
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
  ctx?.revert()
})

async function startDraw() {
  if (rolling.value) return
  error.value = ''
  rolling.value = true
  const started = Date.now()
  try {
    const result = await drawSign({
      category: category.value || undefined,
      question: question.value.trim() || undefined,
    })
    // 摇签动画至少播满 2 秒再接结果
    const remain = Math.max(200, 2000 - (Date.now() - started))
    window.setTimeout(() => {
      const query: Record<string, string> = { fresh: '1' }
      if (result.drawing_id) query.drawing_id = String(result.drawing_id)
      if (question.value.trim()) query.question = question.value.trim()
      if (category.value) query.category = category.value
      router.push({ path: `/sign/${result.sign.no}`, query })
    }, remain)
  } catch (e) {
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
      <div ref="stageEl" class="draw-stage" :class="{ rolling }">
        <div class="tube">
          <div class="tube-sticks">
            <i v-for="n in 7" :key="n" class="stick" :style="{ '--i': n }"></i>
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
          placeholder="所问之事(选填,默念亦可)……"
          :disabled="rolling"
        />
        <div class="chips center-chips">
          <span
            v-for="c in categories"
            :key="c"
            class="chip"
            :class="{ active: category === c }"
            @click="category = category === c ? '' : c"
          >{{ c }}</span>
        </div>
        <button class="btn btn-draw" :disabled="rolling" @click="startDraw">
          {{ rolling ? '摇 签 中' : '摇 签' }}
        </button>
        <div class="field-hint" style="justify-content: center">
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
  font-family: var(--font-song); font-size: 11.5px; color: var(--gold);
}
.step-sep { width: 26px; height: 1px; background: var(--line-2); }

.ritual-hint { margin: 14px 0 12px; letter-spacing: 0.1em; }

.ritual-form { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.ritual-form .input { max-width: 460px; text-align: center; }
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
  color: var(--gold); font-size: 17px;
  transition: transform 0.18s;
}
.quick-card:hover .quick-arrow { transform: translateY(-50%) translateX(3px); }

@media (max-width: 560px) {
  .quick-links { grid-template-columns: 1fr; }
}
</style>
