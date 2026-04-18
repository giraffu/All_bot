import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/profile'
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/Profile.vue')
      },
      {
        path: 'custom-features',
        name: 'CustomFeatures',
        component: () => import('@/views/CustomFeatures.vue')
      },
      {
        path: 'face-swap',
        name: 'FaceSwap',
        component: () => import('@/views/FaceSwap.vue')
      },
      {
        path: 'video-swap',
        name: 'VideoSwap',
        component: () => import('@/views/VideoSwap.vue')
      },
      {
        path: 'single-image',
        name: 'SingleImage',
        component: () => import('@/views/SingleImage.vue')
      },
      {
        path: 'image-prompt',
        name: 'ImageAndPrompt',
        component: () => import('@/views/ImageAndPrompt.vue')
      },
      {
        path: 'single-image-video',
        name: 'SingleImageToVideo',
        component: () => import('@/views/SingleImageToVideo.vue')
      },
      {
        path: 'history',
        name: 'History',
        component: () => import('@/views/History.vue')
      },
      {
        path: 'gallery',
        name: 'Gallery',
        component: () => import('@/views/Gallery.vue')
      },
      {
        path: 'my-submissions',
        name: 'MySubmissions',
        component: () => import('@/views/MySubmissions.vue')
      },
      {
        path: 'my-favorites',
        name: 'MyFavorites',
        component: () => import('@/views/MyFavorites.vue')
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  const isAuthenticated = !!authStore.token
  const allowedIdentities = ['内门弟子', '核心弟子', '真传弟子']
  const allowedGroups = ['金丹期', '元婴期', '化神期', '炼虚期', '合体期', '大乘期', '渡劫期']
  
  const hasPermission = authStore.user && (
    allowedIdentities.includes(authStore.user.current_identity) || 
    allowedGroups.includes(authStore.user.user_group)
  )
  
  if (to.meta.requiresAuth && (!isAuthenticated || !hasPermission)) {
    if (isAuthenticated && !hasPermission) {
      import('ant-design-vue').then(({ message }) => {
        message.error('权限不足：只有金丹期及以上境界，或内门及以上身份的弟子才能登录 Web 端')
      })
      authStore.logout()
    }
    next('/login')
  } else if (to.path === '/login' && isAuthenticated && hasPermission) {
    next('/profile')
  } else {
    next()
  }
})

export default router
