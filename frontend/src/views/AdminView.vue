<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { refreshAdminFlag } from '../store/auth'
import { renderRichText } from '../utils/richtext'
import {
  adminAssistantLogs,
  adminDeleteDrawing,
  adminDeleteUser,
  adminDrawings,
  adminGetSettings,
  adminKbRebuild,
  adminKbStatus,
  adminLoginLogs,
  adminOverview,
  adminResetUserPassword,
  adminSetUserStatus,
  adminTestLLM,
  adminUpdateSettings,
  adminUsers,
  getAdminToken,
  setAdminToken,
  type AdminDrawing,
  type AdminOverview,
  type AdminSettings,
  type AdminUser,
  type AssistantLogItem,
  type KbStatus,
  type LoginLogItem,
} from '../api'

const PAGE_SIZE = 20
const LOG_PAGE_SIZE = 50

type TabKey = 'overview' | 'drawings' | 'users' | 'logs' | 'assistant' | 'settings'
const tabs: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '概览' },
  { key: 'drawings', label: '签文记录' },
  { key: 'users', label: '用户管理' },
  { key: 'logs', label: '登录日志' },
  { key: 'assistant', label: '助手问答' },
  { key: 'settings', label: 'AI 配置' },
]

const token = ref(getAdminToken())
const tab = ref<TabKey>('overview')
const error = ref('')
const notice = ref('')
const busy = ref(false)

const overview = ref<AdminOverview | null>(null)

const drawings = ref<AdminDrawing[]>([])
const drawingTotal = ref(0)
const drawingPage = ref(0)

const users = ref<AdminUser[]>([])
const userQuery = ref('')
const appliedQuery = ref('')
const resetUserId = ref<number | null>(null)
const resetPassword = ref('')

const logs = ref<LoginLogItem[]>([])
const logTotal = ref(0)
const logPage = ref(0)
const logOnlyFailed = ref(false)

const alogs = ref<AssistantLogItem[]>([])
const alTotal = ref(0)
const alPage = ref(0)
const alOnlyBad = ref(false)
const alStats = ref({ up: 0, down: 0, unrated: 0 })
const alExpanded = ref<number | null>(null)

const settings = ref<AdminSettings | null>(null)
const kb = ref<KbStatus | null>(null)
const aiForm = reactive({
  llm_api_base: '',
  llm_model: '',
  llm_temperature: 0.8,
  llm_max_tokens: 1200,
  llm_thinking: '',
  embedding_model: '',
  apiKeyInput: '',
})
const testResult = ref('')

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

function handleAuthError(e: unknown) {
  const m = msg(e)
  if (m.includes('登录已过期') || m.includes('未登录')) {
    setAdminToken('')
    token.value = ''
    refreshAdminFlag()
    error.value = '登录已过期,请重新登录'
  } else {
    error.value = m
  }
}

function logout() {
  setAdminToken('')
  token.value = ''
  refreshAdminFlag()
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
      await loadUsers()
    } else if (tab.value === 'logs') {
      await loadLogs(0)
    } else if (tab.value === 'assistant') {
      await loadAssistantLogs(0)
    } else if (tab.value === 'settings') {
      await loadSettings()
    }
  } catch (e) {
    handleAuthError(e)
  } finally {
    busy.value = false
  }
}

watch(tab, loadTab)
onMounted(() => {
  if (token.value) loadTab()
})

// ---------- 签文记录 ----------
async function loadDrawings(page: number) {
  const data = await adminDrawings(PAGE_SIZE, page * PAGE_SIZE)
  drawings.value = data.items
  drawingTotal.value = data.total
  drawingPage.value = page
}

async function removeDrawing(item: AdminDrawing) {
  if (!window.confirm(`删除第 ${item.sign_no} 签的抽签记录?\n关联的解签与追问记录会一并删除,不可恢复。`)) return
  try {
    await adminDeleteDrawing(item.drawing_id)
    notice.value = `已删除记录 #${item.drawing_id}`
    await loadDrawings(drawingPage.value)
  } catch (e) {
    handleAuthError(e)
  }
}

// ---------- 用户管理 ----------
async function loadUsers() {
  users.value = (await adminUsers(appliedQuery.value || undefined)).items
  resetUserId.value = null
}

function searchUsers() {
  appliedQuery.value = userQuery.value.trim()
  loadUsers().catch(handleAuthError)
}

function clearSearch() {
  userQuery.value = ''
  appliedQuery.value = ''
  loadUsers().catch(handleAuthError)
}

function askReset(u: AdminUser) {
  resetUserId.value = resetUserId.value === u.id ? null : u.id
  resetPassword.value = ''
}

async function doResetPassword(u: AdminUser) {
  if (resetPassword.value.length < 6) {
    error.value = '新密码至少 6 位'
    return
  }
  try {
    await adminResetUserPassword(u.id, resetPassword.value)
    notice.value = `已重置「${u.username}」的密码`
    resetUserId.value = null
    resetPassword.value = ''
  } catch (e) {
    handleAuthError(e)
  }
}

async function toggleStatus(u: AdminUser) {
  const to = !u.is_active
  const word = to ? '启用' : '禁用'
  const extra = to ? '' : '\n禁用后该用户将无法登录,已登录会话也会立即失效。'
  if (!window.confirm(`确定${word}用户「${u.username}」?${extra}`)) return
  try {
    await adminSetUserStatus(u.id, to)
    notice.value = `已${word}「${u.username}」`
    await loadUsers()
  } catch (e) {
    handleAuthError(e)
  }
}

async function removeUser(u: AdminUser) {
  if (!window.confirm(`删除用户「${u.username}」?\n其历史抽签记录会保留(转为匿名)。`)) return
  try {
    await adminDeleteUser(u.id)
    notice.value = `已删除用户「${u.username}」`
    await loadUsers()
  } catch (e) {
    handleAuthError(e)
  }
}

// ---------- 登录日志 ----------
async function loadLogs(page: number) {
  const data = await adminLoginLogs(LOG_PAGE_SIZE, page * LOG_PAGE_SIZE, logOnlyFailed.value)
  logs.value = data.items
  logTotal.value = data.total
  logPage.value = page
}

function toggleOnlyFailed() {
  logOnlyFailed.value = !logOnlyFailed.value
  loadLogs(0).catch(handleAuthError)
}

// ---------- 助手问答 ----------
async function loadAssistantLogs(page: number) {
  const d = await adminAssistantLogs(LOG_PAGE_SIZE, page * LOG_PAGE_SIZE, alOnlyBad.value)
  alogs.value = d.items
  alTotal.value = d.total
  alStats.value = d.stats
  alPage.value = page
  alExpanded.value = null
}

function toggleAlOnlyBad() {
  alOnlyBad.value = !alOnlyBad.value
  loadAssistantLogs(0).catch(handleAuthError)
}

// ---------- AI 配置 ----------
async function loadSettings() {
  const s = await adminGetSettings()
  settings.value = s
  aiForm.llm_api_base = s.llm_api_base
  aiForm.llm_model = s.llm_model
  aiForm.llm_temperature = s.llm_temperature
  aiForm.llm_max_tokens = s.llm_max_tokens
  aiForm.llm_thinking = s.llm_thinking || ''
  aiForm.embedding_model = s.embedding_model || ''
  aiForm.apiKeyInput = ''
  testResult.value = ''
  kb.value = await adminKbStatus()
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
      llm_thinking: aiForm.llm_thinking,
      embedding_model: aiForm.embedding_model.trim(),
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

async function rebuildKb() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const r = await adminKbRebuild()
    kb.value = await adminKbStatus()
    if (r.embedding_error) {
      notice.value = `知识库已重建(关键词检索):${r.chunks} 个切片;向量化未生效 — ${r.embedding_error}`
    } else {
      notice.value = `知识库已重建:${r.chunks} 个切片,检索方式:${r.mode === 'vector' ? '向量' : '关键词'}`
    }
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
const logTotalPages = () => Math.max(1, Math.ceil(logTotal.value / LOG_PAGE_SIZE))
const alTotalPages = () => Math.max(1, Math.ceil(alTotal.value / LOG_PAGE_SIZE))
</script>

<template>
  <!-- 未登录:引导到统一登录入口 -->
  <div v-if="!token" class="admin-login">
    <section class="panel panel-ornate">
      <div class="sec-title" style="justify-content: center">后 台 管 理</div>
      <p class="center muted" style="margin: 6px 0 18px">
        请使用管理员账号登录<br />(与前台共用登录入口,自动识别身份)
      </p>
      <router-link
        class="btn"
        style="display: block; text-align: center; text-decoration: none; box-sizing: border-box"
        to="/login?next=/admin"
      >去 登 录</router-link>
    </section>
  </div>

  <!-- 面板 -->
  <div v-else class="admin">
    <div class="row-between">
      <h2 class="page-title">后 台 管 理</h2>
      <button class="btn ghost small" @click="logout">退出登录</button>
    </div>

    <div class="tabs">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="tab"
        :class="{ active: tab === t.key }"
        @click="tab = t.key"
      >{{ t.label }}</button>
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
      <div class="admin-toolbar">
        <input
          v-model="userQuery"
          class="input"
          style="max-width: 240px"
          placeholder="搜索用户名 / 昵称"
          @keyup.enter="searchUsers"
        />
        <button class="btn ghost small" @click="searchUsers">搜 索</button>
        <button v-if="appliedQuery" class="btn-link" @click="clearSearch">清空「{{ appliedQuery }}」</button>
        <span class="muted" style="margin-left: auto">共 {{ users.length }} 位用户</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>用户名</th><th>昵称</th><th>注册时间</th><th>抽签数</th><th>最近抽签</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="u in users" :key="u.id">
              <tr>
                <td>{{ u.id }}</td>
                <td>{{ u.username || '—' }}</td>
                <td>{{ u.nickname || '—' }}</td>
                <td class="nowrap">{{ fmtDate(u.created_at) }}</td>
                <td>{{ u.drawings }}</td>
                <td class="nowrap">{{ fmtDate(u.last_drawing_at) }}</td>
                <td class="nowrap">
                  <span class="status-dot" :class="u.is_active ? 'on' : 'off'"></span>
                  {{ u.is_active ? '启用' : '禁用' }}
                </td>
                <td class="nowrap">
                  <button class="btn-link" @click="askReset(u)">重置密码</button>
                  <button class="btn-link" @click="toggleStatus(u)">{{ u.is_active ? '禁用' : '启用' }}</button>
                  <button class="btn-link danger" @click="removeUser(u)">删除</button>
                </td>
              </tr>
              <tr v-if="resetUserId === u.id" class="reset-row">
                <td colspan="8">
                  <div class="reset-form">
                    <span class="muted">为「{{ u.username }}」设置新密码:</span>
                    <input
                      v-model="resetPassword"
                      class="input"
                      type="password"
                      maxlength="64"
                      placeholder="新密码(≥6 位)"
                      style="max-width: 220px"
                      @keyup.enter="doResetPassword(u)"
                    />
                    <button class="btn small" @click="doResetPassword(u)">保 存</button>
                    <button class="btn ghost small" @click="resetUserId = null">取 消</button>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!users.length"><td colspan="8" class="center muted">暂无用户</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 登录日志 -->
    <div v-else-if="tab === 'logs'" class="panel" style="padding: 14px 18px">
      <div class="admin-toolbar">
        <button class="chip" :class="{ active: logOnlyFailed }" @click="toggleOnlyFailed">只看失败</button>
        <span class="muted" style="margin-left: auto">共 {{ logTotal }} 条事件</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>时间</th><th>身份</th><th>用户名</th><th>事件</th><th>结果</th><th>IP</th><th>设备</th></tr>
          </thead>
          <tbody>
            <tr v-for="l in logs" :key="l.id">
              <td class="nowrap">{{ fmtDate(l.created_at) }}</td>
              <td><span class="role-chip" :class="l.role">{{ l.role === 'admin' ? '管理员' : '用户' }}</span></td>
              <td>{{ l.username }}</td>
              <td>{{ l.action === 'register' ? '注册' : '登录' }}</td>
              <td class="nowrap">
                <span class="status-dot" :class="l.success ? 'on' : 'fail'"></span>
                {{ l.success ? '成功' : (l.reason || '失败') }}
              </td>
              <td class="mono">{{ l.ip || '—' }}</td>
              <td class="cell-ua" :title="l.user_agent || ''">{{ l.user_agent || '—' }}</td>
            </tr>
            <tr v-if="!logs.length"><td colspan="7" class="center muted">暂无日志</td></tr>
          </tbody>
        </table>
      </div>
      <div v-if="logTotal > LOG_PAGE_SIZE" class="pager">
        <button class="btn ghost small" :disabled="logPage === 0" @click="loadLogs(logPage - 1)">上一页</button>
        <span class="muted">{{ logPage + 1 }} / {{ logTotalPages() }} 页 · 共 {{ logTotal }} 条</span>
        <button class="btn ghost small" :disabled="logPage + 1 >= logTotalPages()" @click="loadLogs(logPage + 1)">下一页</button>
      </div>
    </div>

    <!-- 助手问答 -->
    <div v-else-if="tab === 'assistant'" class="panel" style="padding: 14px 18px">
      <div class="admin-toolbar">
        <button class="chip" :class="{ active: alOnlyBad }" @click="toggleAlOnlyBad">只看踩</button>
        <span class="muted" style="margin-left: auto">
          共 {{ alTotal }} 条 · 👍 {{ alStats.up }} · 👎 {{ alStats.down }} · 未评 {{ alStats.unrated }}
        </span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>时间</th><th>用户</th><th>问题</th><th>回答</th><th>检索</th><th>评价</th></tr>
          </thead>
          <tbody>
            <template v-for="l in alogs" :key="l.id">
              <tr class="clickable" @click="alExpanded = alExpanded === l.id ? null : l.id">
                <td class="nowrap">{{ fmtDate(l.created_at) }}</td>
                <td class="nowrap">{{ l.user }}</td>
                <td class="cell-question">{{ l.question }}</td>
                <td class="cell-answer">
                  {{ alExpanded === l.id ? '▲ 收起' : l.answer.slice(0, 36) + (l.answer.length > 36 ? '… ▼' : ' ▼') }}
                </td>
                <td class="nowrap">{{ l.mode === 'vector' ? '向量' : '关键词' }}</td>
                <td class="nowrap">
                  <span class="vote-tag" :class="l.feedback === 1 ? 'up' : l.feedback === -1 ? 'down' : 'none'">
                    {{ l.feedback === 1 ? '👍 赞' : l.feedback === -1 ? '👎 踩' : '未评' }}
                  </span>
                </td>
              </tr>
              <tr v-if="alExpanded === l.id">
                <td colspan="6" class="al-detail">
                  <div class="msg-content" v-html="renderRichText(l.answer)"></div>
                  <div v-if="l.sources.length" class="assistant-sources">
                    参考:<span v-for="s in l.sources" :key="s.section">《{{ s.section }}》</span>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!alogs.length"><td colspan="6" class="center muted">暂无问答记录</td></tr>
          </tbody>
        </table>
      </div>
      <div v-if="alTotal > LOG_PAGE_SIZE" class="pager">
        <button class="btn ghost small" :disabled="alPage === 0" @click="loadAssistantLogs(alPage - 1)">上一页</button>
        <span class="muted">{{ alPage + 1 }} / {{ alTotalPages() }} 页 · 共 {{ alTotal }} 条</span>
        <button class="btn ghost small" :disabled="alPage + 1 >= alTotalPages()" @click="loadAssistantLogs(alPage + 1)">下一页</button>
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
        <div class="form-row">
          <label class="form-label" for="ai-thinking">思考模式(推理型模型)</label>
          <select id="ai-thinking" v-model="aiForm.llm_thinking" class="input">
            <option value="">跟随模型默认</option>
            <option value="disabled">关闭思考(响应更快,推荐解签)</option>
          </select>
        </div>
        <div class="form-row">
          <label class="form-label" for="ai-embed">向量模型 (Embedding · 使用助手)</label>
          <input
            id="ai-embed"
            v-model="aiForm.embedding_model"
            class="input"
            maxlength="64"
            placeholder="留空=关键词检索,如 doubao-embedding-text-240715"
          />
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

      <div class="sec-title" style="margin-top: 26px">使用助手知识库</div>
      <div v-if="kb" class="kb-card">
        <div class="kb-stats">
          <span>切片数 <b>{{ kb.chunks }}</b></span>
          <span>已向量化 <b>{{ kb.embedded }}</b></span>
          <span>检索方式 <b>{{ kb.embedded > 0 ? '向量' : '关键词' }}</b></span>
          <span>上次构建 <b>{{ fmtDate(kb.last_built_at) }}</b></span>
        </div>
        <p class="muted" style="margin: 8px 0 12px; font-size: 12.5px; line-height: 1.8">
          语料为 <code>docs/</code> 下的用户手册 / FAQ / 管理手册;修改文档后点「重建知识库」生效。
          填写上方 Embedding 模型并重建后,检索自动升级为向量模式(回答更准)。
        </p>
        <button class="btn ghost" :disabled="busy" @click="rebuildKb">重 建 知 识 库</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin { display: flex; flex-direction: column; gap: 18px; }
.admin-login { max-width: 420px; margin: 40px auto 0; }
.form-label {
  display: block; font-size: 13px; color: var(--ink-2);
  letter-spacing: 0.08em; margin-bottom: 5px;
}
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; }
.form-row-wide { grid-column: 1 / -1; }
@media (max-width: 700px) { .form-grid { grid-template-columns: 1fr; } }
</style>
