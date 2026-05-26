import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore, checkWebAccess } from '@/stores/auth'
import {
  confirmTemplateApplyClose,
  useTemplateApplyStore
} from '@/stores/templateApply'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false, bypassTemplateApplyGuard: true }
  },
  {
    path: '/maintenance',
    name: 'Maintenance',
    component: () => import('@/views/Maintenance.vue'),
    meta: { requiresAuth: false, bypassTemplateApplyGuard: true }
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
        path: 'text-to-image',
        name: 'TextToImage',
        component: () => import('@/views/TextToImage.vue')
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
        redirect: {
          name: 'MyFavorites',
          query: { tab: 'submissions' }
        }
      },
      {
        path: 'my-favorites',
        name: 'MyFavorites',
        component: () => import('@/views/MyFavorites.vue')
      },
      {
        path: 'billing',
        name: 'Billing',
        component: () => import('@/views/Billing.vue')
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

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  const templateApplyStore = useTemplateApplyStore()
  const isAuthenticated = !!authStore.token
  const hasPermission = checkWebAccess(authStore.user)

  if (templateApplyStore.visible) {
    if (to.meta.bypassTemplateApplyGuard) {
      await templateApplyStore.confirmCloseAndCleanup('route_leave')
    } else {
      const closeResult = await templateApplyStore.requestClose('route_leave')
      if (closeResult.status === 'blocked') {
        return false
      }

      if (closeResult.status === 'confirm_required') {
        const confirmed = await confirmTemplateApplyClose(closeResult.confirmReason)
        if (!confirmed) {
          return false
        }
      }

      await templateApplyStore.confirmCloseAndCleanup('route_leave')
    }
  }

  if (to.meta.requiresAuth && (!isAuthenticated || !hasPermission)) {
    if (isAuthenticated && !hasPermission) {
      import('ant-design-vue').then(({ message }) => {
        message.error('权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录 Web 端')
      })
      authStore.logout()
    }
    return '/login'
  }

  if (to.path === '/login' && isAuthenticated && hasPermission) {
    return '/profile'
  }

  return true
})

export default router
