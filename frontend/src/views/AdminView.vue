<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import {
  adminDeleteDrawing,
  adminDeleteUser,
  adminDrawings,
  adminGetSettings,
  adminLogin,
  adminOverview,
  adminTestLLM,
  adminUpdateSettings,
  adminUsers,
  getAdminToken,
  setAdminToken,
  type AdminDrawing,
  type AdminOverview,
  type AdminSettings,
  type AdminUser,
} from '../api'

const PAGE_SIZE = 20

const token = ref(getAdminToken())
const loginForm = reactive({ username: 'admin', password: '' })
const loginError = ref('')
const loggingIn = ref(false)

const tab = ref<'overview' | 'drawings' | 'users' | 'settings'>('overview')
const error = ref('')
const notice = ref('')
const busy = ref(false)

const overview = ref<AdminOverview | null>(null)
const drawings = ref<AdminDrawing[]>([])
const drawingTotal = ref(0)
const drawingPage = ref(0)
const users = ref<AdminUser[]>([])
const settings = ref<AdminSettings | null>(null)

const aiForm = reactive({
  llm_api_base: '',
  llm_model: '',
  llm_temperature: 0.8,
  llm_max_tokens: 1200,
  apiKeyInput: '',
})
const testResult = ref('')

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

function handleAuthError(e: unknown) {
  const m = msg(e)
  if (m.includes('登录')) {
    setAdminToken('')
    token.value = ''
    loginError.value = m
  } else {
    error.value = m
  }
}

async function doLogin() {
  if (loggingIn.value) return
  loggingIn.value = true
  loginError.value = ''
  try {
    await adminLogin(loginForm.username.trim(), loginForm.password)
    token.value = getAdminToken()
    await loadTab()
  } catch (e) {
    loginError.value = msg(e)
  } finally {
    loggingIn.value = false
  }
}

function logout() {
  setAdminToken('')
  token.value = ''
  loginForm.password = ''
}

async function loadTab() {
  if (!token.value) return
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    if (tab.value === 'overview') {
      overview.value = await adminOverview()
    } else if (tab.value === 'drawings') {
      await loadDrawings(0)
    } else if (tab.value === 'users') {
      users.value = (await adminUsers()).items
    } else if (tab.value === 'settings') {
      await loadSettings()
    }
  } catch (e) {
    handleAuthError(e)
  } finally {
    busy.value = false
  }
}

async function loadDrawings(page: number) {
  const data = await adminDrawings(PAGE_SIZE, page * PAGE_SIZE)
  drawings.value = data.items
  drawingTotal.value = data.total
  drawingPage.value = page
}

watch(tab, loadTab)
onMounted(() => {
  if (token.value) loadTab()
})

async function removeDrawing(item: AdminDrawing) {
  if (!window.confirm(`删除第 ${item.sign_no} 签的抽签记录?\n关联的解签与追问记录会一并删除,不可恢复。`)) return
  try {
    await adminDeleteDrawing(item.drawing_id)
    notice.value = `已删除记录 #${item.drawing_id}`
    await loadTab()
  } catch (e) {
    handleAuthError(e)
  }
}

async function removeUser(item: AdminUser) {
  if (!window.confirm(`删除用户 #${item.id}?\n其历史抽签记录会保留(转为匿名)。`)) return
  try {
    await adminDeleteUser(item.id)
    notice.value = `已删除用户 #${item.id}`
    await loadTab()
  } catch (e) {
    handleAuthError(e)
  }
}

// ---------- AI 配置 ----------
async function loadSettings() {
  const s = await adminGetSettings()
  settings.value = s
  aiForm.llm_api_base = s.llm_api_base
  aiForm.llm_model = s.llm_model
  aiForm.llm_temperature = s.llm_temperature
  aiForm.llm_max_tokens = s.llm_max_tokens
  aiForm.apiKeyInput = ''
  testResult.value = ''
}

async function saveSettings() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const payload: Record<string, string | number> = {
      llm_api_base: aiForm.llm_api_base.trim(),
      llm_model: aiForm.llm_model.trim(),
      llm_temperature: aiForm.llm_temperature,
      llm_max_tokens: aiForm.llm_max_tokens,
    }
    if (aiForm.apiKeyInput.trim()) payload.llm_api_key = aiForm.apiKeyInput.trim()
    settings.value = await adminUpdateSettings(payload)
    aiForm.apiKeyInput = ''
    notice.value = '配置已保存,立即生效(无需重启服务)'
  } catch (e) {
    handleAuthError(e)
  } finally {
    busy.value = false
  }
}

async function clearKey() {
  if (!window.confirm('确定清除 API Key?\n清除后 AI 解签将不可用(静态签文不受影响)。')) return
  busy.value = true
  try {
    settings.value = await adminUpdateSettings({ llm_api_key: '' })
    notice.value = 'API Key 已清除'
  } catch (e) {
    handleAuthError(e)
  } finally {
    busy.value = false
  }
}

async function testLLM() {
  testResult.value = '测试中……'
  try {
    const r = await adminTestLLM()
    testResult.value = `✓ 连接成功 · 模型 ${r.model} · 延迟 ${r.latency_ms}ms · 回复「${r.reply}」`
  } catch (e) {
    testResult.value = `✗ ${msg(e)}`
  }
}

// ---------- 展示辅助 ----------
function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const totalPages = () => Math.max(1, Math.ceil(drawingTotal.value / PAGE_SIZE))
</script>

<template>
  <!-- 登录 -->
  <div v-if="!token" class="admin-login">
    <section class="panel panel-ornate">
      <div class="sec-title" style="justify-content: center">后 台 登 录</div>
      <form @submit.prevent="doLogin">
        <label class="form-label" for="admin-username">管理员</label>
        <input
          id="admin-username"
          v-model="loginForm.username"
          class="input"
          maxlength="64"
          autocomplete="username"
        />
        <label class="form-label" style="margin-top: 12px" for="admin-password">密码</label>
        <input
          id="admin-password"
          v-model="loginForm.password"
          class="input"
          type="password"
          maxlength="128"
          autocomplete="current-password"
          placeholder="在 backend/.env 配置 ADMIN_PASSWORD"
        />
        <div v-if="loginError" class="banner error" style="margin: 12px 0 0">{{ loginError }}</div>
        <button class="btn" style="width: 100%; margin-top: 16px" :disabled="loggingIn" type="submit">
          {{ loggingIn ? '登 录 中…' : '登 录' }}
        </button>
      </form>
    </section>
  </div>

  <!-- 面板 -->
  <div v-else class="admin">
    <div class="row-between">
      <h2 class="page-title">后 台 管 理</h2>
      <button class="btn ghost small" @click="logout">退出登录</button>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'overview' }" @click="tab = 'overview'">概览</button>
      <button class="tab" :class="{ active: tab === 'drawings' }" @click="tab = 'drawings'">签文记录</button>
      <button class="tab" :class="{ active: tab === 'users' }" @click="tab = 'users'">用户管理</button>
      <button class="tab" :class="{ active: tab === 'settings' }" @click="tab = 'settings'">AI 配置</button>
    </div>

    <div v-if="error" class="banner error">{{ error }}</div>
    <div v-if="notice" class="banner info">{{ notice }}</div>

    <!-- 概览 -->
    <div v-if="tab === 'overview' && overview" class="stat-grid">
      <div class="stat-card"><div class="stat-num">{{ overview.drawings }}</div><div class="stat-label">抽签总数</div></div>
      <div class="stat-card"><div class="stat-num">{{ overview.drawings_today }}</div><div class="stat-label">今日抽签</div></div>
      <div class="stat-card"><div class="stat-num">{{ overview.readings }}</div><div class="stat-label">AI 解签</div></div>
      <div class="stat-card"><div class="stat-num">{{ overview.messages }}</div><div class="stat-label">追问消息</div></div>
      <div class="stat-card"><div class="stat-num">{{ overview.users }}</div><div class="stat-label">注册用户</div></div>
      <div class="stat-card ai-stat">
        <div class="stat-label">AI 解签状态</div>
        <div class="stat-num-small" :class="overview.ai.configured ? 'ok' : 'off'">
          {{ overview.ai.configured ? '已配置' : '未配置' }}
        </div>
        <div class="muted">{{ overview.ai.model }}</div>
      </div>
    </div>

    <!-- 签文记录 -->
    <div v-else-if="tab === 'drawings'" class="panel" style="padding: 14px 18px">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>时间</th><th>签文</th><th>分类</th><th>所问</th><th>解签</th><th>追问</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in drawings" :key="it.drawing_id">
              <td>{{ it.drawing_id }}</td>
              <td class="nowrap">{{ fmtDate(it.created_at) }}</td>
              <td>
                <router-link :to="`/sign/${it.sign_no}`">{{ it.title }}</router-link>
                <div v-if="it.excerpt" class="cell-excerpt">{{ it.excerpt }}…</div>
              </td>
              <td>{{ it.category || '—' }}</td>
              <td class="cell-question">{{ it.question || '—' }}</td>
              <td>{{ it.reading_id ? (it.reading_model || '有') : '—' }}</td>
              <td>{{ it.messages }}</td>
              <td><button class="btn-link danger" @click="removeDrawing(it)">删除</button></td>
            </tr>
            <tr v-if="!drawings.length"><td colspan="8" class="center muted">暂无记录</td></tr>
          </tbody>
        </table>
      </div>
      <div v-if="drawingTotal > PAGE_SIZE" class="pager">
        <button class="btn ghost small" :disabled="drawingPage === 0" @click="loadDrawings(drawingPage - 1)">上一页</button>
        <span class="muted">{{ drawingPage + 1 }} / {{ totalPages() }} 页 · 共 {{ drawingTotal }} 条</span>
        <button class="btn ghost small" :disabled="drawingPage + 1 >= totalPages()" @click="loadDrawings(drawingPage + 1)">下一页</button>
      </div>
    </div>

    <!-- 用户管理 -->
    <div v-else-if="tab === 'users'" class="panel" style="padding: 14px 18px">
      <p class="muted" style="margin: 0 0 10px">
        当前为匿名模式,用户表通常为空;登录体系上线后此处管理注册用户。删除用户不会删除其历史抽签记录。
      </p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>#</th><th>openid</th><th>昵称</th><th>注册时间</th><th>抽签数</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.id }}</td>
              <td>{{ u.openid || '—' }}</td>
              <td>{{ u.nickname || '—' }}</td>
              <td class="nowrap">{{ fmtDate(u.created_at) }}</td>
              <td>{{ u.drawings }}</td>
              <td><button class="btn-link danger" @click="removeUser(u)">删除</button></td>
            </tr>
            <tr v-if="!users.length"><td colspan="6" class="center muted">暂无用户</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- AI 配置 -->
    <div v-else-if="tab === 'settings' && settings" class="panel">
      <div class="sec-title">AI 解签配置</div>
      <p class="muted" style="margin: 0 0 16px">
        配置保存后立即生效(数据库优先于 backend/.env);密钥仅保存于本机数据库,页面只展示末 4 位。
      </p>
      <div class="form-grid">
        <div class="form-row">
          <label class="form-label" for="ai-base">接口地址 (base_url)</label>
          <input id="ai-base" v-model="aiForm.llm_api_base" class="input" maxlength="256" placeholder="https://open.bigmodel.cn/api/paas/v4" />
        </div>
        <div class="form-row">
          <label class="form-label" for="ai-model">模型</label>
          <input id="ai-model" v-model="aiForm.llm_model" class="input" maxlength="64" placeholder="glm-4-flash" />
        </div>
        <div class="form-row">
          <label class="form-label" for="ai-temp">温度 (0–2)</label>
          <input id="ai-temp" v-model.number="aiForm.llm_temperature" class="input" type="number" step="0.05" min="0" max="2" />
        </div>
        <div class="form-row">
          <label class="form-label" for="ai-tokens">最大输出 tokens</label>
          <input id="ai-tokens" v-model.number="aiForm.llm_max_tokens" class="input" type="number" step="64" min="16" max="8192" />
        </div>
        <div class="form-row form-row-wide">
          <label class="form-label" for="ai-key">
            API Key
            <span v-if="settings.llm_api_key_set" class="muted">当前:{{ settings.llm_api_key_masked }}</span>
            <span v-else class="muted">当前未配置</span>
          </label>
          <input
            id="ai-key"
            v-model="aiForm.apiKeyInput"
            class="input"
            type="password"
            maxlength="256"
            :placeholder="settings.llm_api_key_set ? '留空表示不修改' : '粘贴 API Key'"
            autocomplete="new-password"
          />
        </div>
      </div>

      <div class="row-between" style="margin-top: 18px">
        <div class="row-actions">
          <button class="btn" :disabled="busy" @click="saveSettings">保 存 配 置</button>
          <button class="btn ghost" :disabled="busy" @click="testLLM">测 试 连 接</button>
          <button v-if="settings.llm_api_key_set" class="btn ghost" :disabled="busy" @click="clearKey">清除密钥</button>
        </div>
      </div>
      <div v-if="testResult" class="test-result" :class="{ bad: testResult.startsWith('✗') }">{{ testResult }}</div>
    </div>
  </div>
</template>

<style scoped>
.admin { display: flex; flex-direction: column; gap: 18px; }
.admin-login { max-width: 400px; margin: 40px auto 0; }
.form-label {
  display: block; font-size: 13px; color: var(--ink-2);
  letter-spacing: 0.08em; margin-bottom: 5px;
}
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; }
.form-row-wide { grid-column: 1 / -1; }
@media (max-width: 700px) { .form-grid { grid-template-columns: 1fr; } }
</style>
