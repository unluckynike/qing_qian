<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authLogin, authRegister } from '../api'
import { setUserSession } from '../store/auth'

const route = useRoute()
const router = useRouter()

const mode = ref<'login' | 'register'>('login')
const form = reactive({ username: '', password: '', password2: '', nickname: '' })
const error = ref('')
const busy = ref(false)

const isRegister = computed(() => mode.value === 'register')
const title = computed(() => (isRegister.value ? '注 册' : '登 录'))

function switchMode(m: 'login' | 'register') {
  mode.value = m
  error.value = ''
}

async function submit() {
  if (busy.value) return
  error.value = ''
  const username = form.username.trim()
  if (!/^[A-Za-z0-9_]{3,32}$/.test(username)) {
    error.value = '用户名需 3-32 位字母、数字或下划线'
    return
  }
  if (form.password.length < 6) {
    error.value = '密码至少 6 位'
    return
  }
  if (isRegister.value && form.password !== form.password2) {
    error.value = '两次输入的密码不一致'
    return
  }
  busy.value = true
  try {
    const data = isRegister.value
      ? await authRegister(username, form.password, form.nickname.trim() || undefined)
      : await authLogin(username, form.password)
    setUserSession(data.token, data.user)
    const next = typeof route.query.next === 'string' ? route.query.next : '/'
    router.push(next)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <section class="panel panel-ornate">
      <div class="sec-title" style="justify-content: center">{{ title }}</div>

      <div class="auth-tabs">
        <button class="tab" :class="{ active: !isRegister }" @click="switchMode('login')">登录</button>
        <button class="tab" :class="{ active: isRegister }" @click="switchMode('register')">注册</button>
      </div>

      <form @submit.prevent="submit">
        <label class="form-label" for="auth-username">用户名</label>
        <input
          id="auth-username"
          v-model="form.username"
          class="input"
          maxlength="32"
          autocomplete="username"
          placeholder="3-32 位字母、数字或下划线"
        />

        <label class="form-label" style="margin-top: 12px" for="auth-password">密码</label>
        <input
          id="auth-password"
          v-model="form.password"
          class="input"
          type="password"
          maxlength="64"
          :autocomplete="isRegister ? 'new-password' : 'current-password'"
          placeholder="至少 6 位"
        />

        <template v-if="isRegister">
          <label class="form-label" style="margin-top: 12px" for="auth-password2">确认密码</label>
          <input
            id="auth-password2"
            v-model="form.password2"
            class="input"
            type="password"
            maxlength="64"
            autocomplete="new-password"
            placeholder="再次输入密码"
          />
          <label class="form-label" style="margin-top: 12px" for="auth-nickname">昵称(选填)</label>
          <input
            id="auth-nickname"
            v-model="form.nickname"
            class="input"
            maxlength="24"
            autocomplete="nickname"
            placeholder="展示名称,默认同用户名"
          />
        </template>

        <div v-if="error" class="banner error" style="margin: 12px 0 0">{{ error }}</div>
        <button class="btn" style="width: 100%; margin-top: 16px" :disabled="busy" type="submit">
          {{ busy ? '提 交 中…' : title }}
        </button>
      </form>

      <p class="muted center" style="margin: 14px 0 0">
        {{ isRegister ? '已有账号?' : '还没有账号?' }}
        <a href="javascript:;" @click="switchMode(isRegister ? 'login' : 'register')">
          {{ isRegister ? '去登录' : '去注册' }}
        </a>
      </p>
      <p class="muted center" style="margin: 8px 0 0; font-size: 12.5px">
        注册登录后:抽签记录自动归属本人,签事记仅自己可见
      </p>
    </section>
  </div>
</template>

<style scoped>
.auth-page { max-width: 420px; margin: 36px auto 0; }
.auth-tabs { display: flex; gap: 10px; justify-content: center; margin-bottom: 18px; }
</style>
