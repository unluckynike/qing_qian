<script setup lang="ts">
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
        <router-link to="/history">签事记</router-link>
        <router-link to="/admin">管理</router-link>
      </nav>
    </div>
  </header>

  <main class="shell" style="padding: 24px 0 40px">
    <router-view v-slot="{ Component }">
      <transition name="page" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </main>

  <footer class="footer">
    <div class="shell">
      本应用仅供传统文化娱乐参考,请勿迷信 · 签文整理自公开资料,AI 解读仅供参考<br />
      青签 · 吕祖灵签一百签
    </div>
  </footer>
</template>
