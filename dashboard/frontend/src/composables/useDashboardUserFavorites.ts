import { ref } from 'vue'
import message from 'ant-design-vue/es/message'

import { fetchUserFavorites } from '../api/api'

const DEFAULT_PAGE_SIZE = 12

export function useDashboardUserFavorites() {
  const showFavoritesModal = ref(false)
  const selectedFavoritesUser = ref<any | null>(null)
  const favoriteItems = ref<any[]>([])
  const favoritesLoading = ref(false)
  const favoritesPage = ref(1)
  const favoritesPages = ref(0)
  const favoritesTotal = ref(0)
  const favoritesPageSize = ref(DEFAULT_PAGE_SIZE)

  const loadFavorites = async (user: any, page = 1) => {
    favoritesLoading.value = true

    try {
      const payload = await fetchUserFavorites(user.id, {
        page,
        size: favoritesPageSize.value,
      })
      favoriteItems.value = payload.items || []
      favoritesPage.value = payload.page || page
      favoritesPages.value = payload.pages || 0
      favoritesTotal.value = payload.total || 0
    } catch (error: any) {
      console.error('Error fetching user favorites:', error)
      message.error(
        '获取用户收藏失败: ' + (error?.response?.data?.detail || error?.message || '未知错误')
      )
    } finally {
      favoritesLoading.value = false
    }
  }

  const viewFavorites = async (user: any) => {
    selectedFavoritesUser.value = user
    showFavoritesModal.value = true
    favoriteItems.value = []
    favoritesPage.value = 1
    favoritesPages.value = 0
    favoritesTotal.value = 0
    await loadFavorites(user, 1)
  }

  const changeFavoritesPage = async (page: number) => {
    if (!selectedFavoritesUser.value || favoritesLoading.value) {
      return
    }
    await loadFavorites(selectedFavoritesUser.value, page)
  }

  const closeFavoritesModal = () => {
    showFavoritesModal.value = false
    selectedFavoritesUser.value = null
    favoriteItems.value = []
    favoritesPage.value = 1
    favoritesPages.value = 0
    favoritesTotal.value = 0
  }

  return {
    showFavoritesModal,
    selectedFavoritesUser,
    favoriteItems,
    favoritesLoading,
    favoritesPage,
    favoritesPages,
    favoritesPageSize,
    favoritesTotal,
    viewFavorites,
    changeFavoritesPage,
    closeFavoritesModal,
  }
}
