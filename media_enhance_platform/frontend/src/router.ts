import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import HomeView from '@/views/HomeView.vue'
import AuthView from '@/views/AuthView.vue'
import WorkspaceView from '@/views/WorkspaceView.vue'
import PricingView from '@/views/PricingView.vue'
import SupportView from '@/views/SupportView.vue'
import LegalView from '@/views/LegalView.vue'
import AdminView from '@/views/AdminView.vue'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: (to) => (to.hash ? { el: to.hash } : { top: 0 }),
  routes: [
    { path: '/', component: HomeView },
    { path: '/login', component: AuthView },
    { path: '/register', component: AuthView, props: { initialMode: 'register' } },
    { path: '/workspace', component: WorkspaceView, meta: { auth: true } },
    { path: '/pricing', component: PricingView },
    { path: '/support', component: SupportView, meta: { auth: true } },
    { path: '/legal/:document', component: LegalView },
    { path: '/admin', component: AdminView, meta: { auth: true, admin: true } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.bootstrap()
  if (to.meta.auth && !auth.isAuthenticated) return `/login?next=${encodeURIComponent(to.fullPath)}`
  if (to.meta.admin && !auth.isAdmin) return '/workspace'
  if ((to.path === '/login' || to.path === '/register') && auth.isAuthenticated) return '/workspace'
})

export default router
