import { createRouter, createWebHistory } from 'vue-router'
import type { LocationQueryRaw, RouteLocationNormalized, RouteLocationRaw, RouteRecordRaw } from 'vue-router'
import { useAuthStore, checkWebAccess } from '@/stores/auth'
import { getRuntimeFlag } from '@/config/runtime'
import {
  confirmTemplateApplyClose,
  useTemplateApplyStore
} from '@/stores/templateApply'

const redirectToCustomFeatures = (type: string) => (to: { query: Record<string, unknown> }) => ({
  name: 'CustomFeatures',
  query: {
    ...to.query,
    type,
  },
})

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false, bypassTemplateApplyGuard: true }
  },
  ...(import.meta.env.DEV
    ? [{
        path: '/lab-preview',
        name: 'LabPreview',
        component: () => import('@/views/CustomFeatures.vue'),
        meta: { requiresAuth: false, bypassTemplateApplyGuard: true }
      } satisfies RouteRecordRaw]
    : []),
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
      ...(getRuntimeFlag('enable_ltx_t2v', false)
        ? [{
            path: 'characters',
            name: 'Characters',
            component: () => import('@/views/Characters.vue')
          } satisfies RouteRecordRaw]
        : []),
      {
        path: 'face-swap',
        name: 'FaceSwap',
        redirect: redirectToCustomFeatures('face_swap')
      },
      {
        path: 'video-swap',
        name: 'VideoSwap',
        redirect: redirectToCustomFeatures('scail2_face_swap_v2')
      },
      {
        path: 'single-image',
        name: 'SingleImage',
        redirect: redirectToCustomFeatures('random_faceswap')
      },
      {
        path: 'image-prompt',
        name: 'ImageAndPrompt',
        redirect: redirectToCustomFeatures('i2i_pro')
      },
      {
        path: 'text-to-image',
        name: 'TextToImage',
        redirect: redirectToCustomFeatures('txt2img')
      },
      {
        path: 'single-image-video',
        name: 'SingleImageToVideo',
        redirect: redirectToCustomFeatures('custom_video')
      },
      {
        path: 'wan22-video-v2',
        name: 'Wan22VideoV2',
        redirect: redirectToCustomFeatures('wan22_video_v2')
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
        component: () => import('@/views/Billing.vue'),
        meta: { allowsPaymentOnly: true }
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

type RouteLaunchParams = Pick<RouteLocationNormalized, 'fullPath' | 'hash' | 'query'>

const hasTelegramLaunchParams = (to: RouteLaunchParams) => (
  to.hash.includes('tgWebApp')
  || Object.keys(to.query).some((key) => key.startsWith('tgWebApp'))
)

const buildGuestLoginRedirect = (to: RouteLaunchParams): RouteLocationRaw => {
  const targetPath = to.fullPath.split('#', 1)[0]
  const query: LocationQueryRaw = {
    ...(hasTelegramLaunchParams(to) ? to.query as LocationQueryRaw : {}),
    redirect: targetPath,
  }
  return {
    path: '/login',
    query,
    hash: to.hash
  }
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  const templateApplyStore = useTemplateApplyStore()
  const isAuthenticated = !!authStore.token
  const hasPermission = checkWebAccess(authStore.user)
  const allowsPaymentOnly = to.meta.allowsPaymentOnly === true
  const isPaymentSession = authStore.sessionPurpose === 'payment'

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

  const cannotAccessProtectedRoute = (
    isPaymentSession
      ? !allowsPaymentOnly
      : !hasPermission && !allowsPaymentOnly
  )

  if (to.meta.requiresAuth && (!isAuthenticated || cannotAccessProtectedRoute)) {
    if (isAuthenticated && cannotAccessProtectedRoute) {
      import('ant-design-vue').then(({ message }) => {
        message.error('权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录 Web 端')
      })
      authStore.logout()
    }
    return buildGuestLoginRedirect(to)
  }

  if (
    to.path === '/login'
    && isAuthenticated
    && hasPermission
    && !isPaymentSession
  ) {
    return '/profile'
  }

  return true
})

export default router
