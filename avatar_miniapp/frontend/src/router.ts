import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true },
    },
    { path: '/', component: () => import('@/views/StudioView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.guest) return auth.token ? '/' : true
  if (!auth.token) return '/login'
  if (!auth.user && !(await auth.restore())) return '/login'
  return true
})

export default router
