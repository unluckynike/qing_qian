<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth, logoutAll, refreshMe } from './store/auth'

const route = useRoute()
const router = useRouter()
const menuOpen = ref(false)

const displayName = computed(() =>
  auth.user?.nickname || (auth.isAdmin ? '管理员' : ''),
)
const showMenu = computed(() => Boolean(auth.user || auth.isAdmin))

onMounted(refreshMe)
watch(() => route.fullPath, () => (menuOpen.value = false))

function logout() {
  logoutAll()
  menuOpen.value = false
  router.push('/')
}
</script>

<template>
  <header class="topbar">
    <div class="shell topbar-inner">
      <router-link to="/" class="brand">
        <span class="seal">青<br />签</span>
        <span>
          <span class="brand-name">青签</span>
          <span class="brand-sub">吕祖灵签</span>
        </span>
      </router-link>

      <nav class="nav">
        <router-link to="/">求 签</router-link>
        <router-link to="/library">签文库</router-link>
        <router-link v-if="auth.user" to="/history">签事记</router-link>
        <router-link v-if="auth.isAdmin" to="/admin">管理</router-link>
      </nav>

      <div class="nav-auth">
        <router-link v-if="!showMenu" to="/login" class="nav-cta">登录 / 注册</router-link>
        <div v-else class="user-menu">
          <button class="user-chip" @click="menuOpen = !menuOpen">{{ displayName }} ▾</button>
          <div v-if="menuOpen" class="user-drop">
            <router-link v-if="auth.user" to="/history">我的签事记</router-link>
            <router-link v-if="auth.isAdmin" to="/admin">后台管理</router-link>
            <a href="javascript:;" @click="logout">退出登录</a>
          </div>
        </div>
      </div>
    </div>
  </header>

  <main class="shell" style="padding: 24px 0 40px">
    <router-view />
  </main>

  <footer class="footer">
    <div class="shell">
      本应用仅供传统文化娱乐参考,请勿迷信 · 签文整理自公开资料,AI 解读仅供参考<br />
      青签 · 吕祖灵签一百签
    </div>
  </footer>
</template>
