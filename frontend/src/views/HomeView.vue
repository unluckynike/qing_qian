<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { drawSign } from '../api'

const router = useRouter()
const question = ref('')
const category = ref('')
const rolling = ref(false)
const error = ref('')
const categories = ['事业', '姻缘', '财运', '健康', '其他']

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
  <div class="home">
    <div class="hero center reveal">
      <div class="hero-mark">☯</div>
      <h1 class="hero-title">青签</h1>
      <div class="hero-sub">吕祖灵签 · 一百签</div>
      <div class="hero-line"></div>
    </div>

    <div class="panel panel-ornate reveal d1">
      <div class="sec-title">诚心默念所问之事</div>
      <textarea
        v-model="question"
        class="textarea"
        maxlength="100"
        placeholder="可在心中默念,也可写下所问之事(选填)……"
        :disabled="rolling"
      ></textarea>
      <div class="field-hint">
        <span>心诚则灵,一事一签</span>
        <span>{{ question.length }}/100</span>
      </div>
      <div class="chips" style="margin-top: 16px">
        <span
          v-for="c in categories"
          :key="c"
          class="chip"
          :class="{ active: category === c }"
          @click="category = category === c ? '' : c"
        >{{ c }}</span>
      </div>
    </div>

    <div class="panel reveal d2" style="text-align: center; padding-top: 34px">
      <div class="draw-stage" :class="{ rolling }">
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

      <p class="muted" style="margin: 22px 0 18px">
        {{ rolling ? '签筒摇动中,静候落签……' : '静心凝神,摇动签筒' }}
      </p>
      <button class="btn" :disabled="rolling" @click="startDraw">
        {{ rolling ? '摇 签 中' : '摇 签' }}
      </button>

      <div v-if="error" class="banner error" style="text-align: left">{{ error }}</div>
    </div>

    <p class="center muted reveal d3" style="margin-top: 22px">
      或先浏览
      <router-link to="/library">签文库</router-link>
      ,了解吕祖灵签一百签
    </p>
  </div>
</template>

<style scoped>
.hero { padding: 26px 0 30px; }
.hero-mark { font-size: 30px; color: var(--gold); line-height: 1; }
.hero-title {
  font-family: var(--font-song);
  font-size: clamp(46px, 11vw, 74px);
  font-weight: 700;
  letter-spacing: 0.22em;
  text-indent: 0.22em;
  margin: 10px 0 8px;
}
.hero-sub { color: var(--ink-2); letter-spacing: 0.5em; text-indent: 0.5em; font-size: 15px; }
.hero-line {
  width: 130px; height: 2px; margin: 22px auto 0;
  background: linear-gradient(90deg, transparent, var(--gold-2), transparent);
  position: relative;
}
.hero-line::after {
  content: ""; position: absolute; left: 50%; top: -2.5px;
  width: 7px; height: 7px; background: var(--gold); transform: translateX(-50%) rotate(45deg);
}
</style>
