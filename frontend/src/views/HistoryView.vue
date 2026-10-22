<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchHistory, type HistoryItem } from '../api'

const router = useRouter()
const items = ref<HistoryItem[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const data = await fetchHistory(30)
    items.value = data.items
  } catch (e) {
    const m = e instanceof Error ? e.message : String(e)
    if (m.includes('登录')) {
      // 令牌过期:回登录页并回跳
      router.push({ name: 'login', query: { next: '/history' } })
      return
    }
    error.value = m
  } finally {
    loading.value = false
  }
})

function fmt(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function open(item: HistoryItem) {
  router.push(`/sign/${item.sign_no}?drawing_id=${item.drawing_id}`)
}
</script>

<template>
  <div>
    <h2 class="page-title reveal">签 事 记</h2>
    <p class="muted reveal d1" style="margin-top: 6px">我的抽签与解签记录(仅本人可见,留存最近三十次)</p>

    <div v-if="error" class="banner error">{{ error }}</div>
    <div v-else-if="loading" class="center muted" style="padding: 50px 0">加载中……</div>

    <div v-else-if="!items.length" class="panel center reveal d1" style="padding: 46px 24px">
      <p class="muted" style="margin: 0 0 18px">还没有摇过签,去试试手气?</p>
      <button class="btn" @click="router.push('/')">去 求 签</button>
    </div>

    <div v-else class="panel reveal d2" style="padding-top: 8px; padding-bottom: 8px">
      <button v-for="it in items" :key="it.drawing_id" type="button" class="hist-item" @click="open(it)">
        <span class="hist-date">{{ fmt(it.created_at) }}</span>
        <span style="flex: 1; min-width: 0">
          <span class="hist-title">{{ it.title }}</span>
          <span class="hist-meta">
            <span v-if="it.category" class="chip-sm">{{ it.category }}</span>
            <span v-if="it.question">「{{ it.question }}」</span>
          </span>
          <span v-if="it.excerpt" class="hist-excerpt">{{ it.excerpt }}…</span>
        </span>
      </button>
    </div>
  </div>
</template>
