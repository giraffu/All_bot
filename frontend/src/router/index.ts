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
        path: 'lazy-features',
        name: 'LazyFeatures',
        component: () => import('@/views/LazyFeatures.vue')
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
  
  if (to.meta.requiresAuth && !isAuthenticated) {
    next('/login')
  } else if (to.path === '/login' && isAuthenticated) {
    next('/profile')
  } else {
    next()
  }
})

export default router
