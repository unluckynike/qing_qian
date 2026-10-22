<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchSigns, type SignBrief } from '../api'

const router = useRouter()
const signs = ref<SignBrief[]>([])
const query = ref('')
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const data = await fetchSigns()
    signs.value = data.signs
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})

const filtered = computed(() => {
  const q = query.value.trim()
  if (!q) return signs.value
  return signs.value.filter(
    (s) => String(s.no).includes(q) || s.title.includes(q) || s.ancient.includes(q),
  )
})

function luckyClassOf(lucky: string): string {
  if (lucky.startsWith('上')) return 'lv-shang'
  if (lucky.startsWith('中下') || lucky.startsWith('下')) return 'lv-xia'
  return 'lv-zhong'
}
</script>

<template>
  <div>
    <div class="row-between reveal">
      <h2 class="page-title">吕祖灵签 · 一百签</h2>
      <input v-model="query" class="input" style="width: 210px" placeholder="按签号 / 签意检索" />
    </div>

    <div v-if="error" class="banner error">{{ error }}</div>
    <div v-else-if="loading" class="center muted" style="padding: 50px 0">签文库加载中……</div>

    <div v-else class="lib-grid" style="margin-top: 22px">
      <button v-for="s in filtered" :key="s.no" type="button" class="lib-card" @click="router.push(`/sign/${s.no}`)">
        <span class="lib-no">
          第 {{ s.no }} 签
          <span v-if="s.lucky" class="lucky-badge sm" :class="luckyClassOf(s.lucky)">{{ s.lucky }}</span>
        </span>
        <span class="lib-title">{{ s.ancient }}</span>
        <span class="lib-ancient">{{ s.title }}</span>
      </button>
    </div>

    <p v-if="!loading && !error" class="center muted" style="margin-top: 22px">
      {{ filtered.length }} / {{ signs.length }} 签
    </p>
  </div>
</template>
