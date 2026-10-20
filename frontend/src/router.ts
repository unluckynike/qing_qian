import { createRouter, createWebHashHistory } from 'vue-router'
import { auth } from './store/auth'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('./views/HomeView.vue') },
    { path: '/sign/:no', name: 'sign', component: () => import('./views/SignView.vue'), props: true },
    { path: '/library', name: 'library', component: () => import('./views/LibraryView.vue') },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue') },
    { path: '/admin', name: 'admin', component: () => import('./views/AdminView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

// 签事记需要登录(登录后回跳)
router.beforeEach((to) => {
  if (to.name === 'history' && !auth.token) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  return true
})
