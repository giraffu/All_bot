import api from '@/api'
import type {
  ApplyContextSource,
  GalleryPost,
  HistoryItem,
  LibraryCollectionScope,
  LtxHistoryChainResponse,
  PaginatedGalleryResponse,
  RecentHistoryResponse,
  Wan22HistoryChainResponse,
} from '@/types/gallery'
import type { RawApplyContextResponse } from '@/types/templateApply'

interface MyLibraryPostsParams {
  scope: LibraryCollectionScope
  page: number
  size: number
  taskType?: string
}

interface GalleryCommentsPage {
  items: unknown[]
  total: number
  page: number
  size: number
  pages: number
}

export interface PromptUnlockResponse {
  post_id: number
  prompt: string
  prompt_unlocked: boolean
  prompt_unlockable: boolean
  prompt_is_masked: boolean
  prompt_unlock_price: number
  current_credits: number
  already_unlocked: boolean
}

export type GalleryReportReason = 'children' | 'gore' | 'gross' | 'other'

export interface GalleryReportSubmitResponse {
  status: string
  report_id: number
}

export async function getRecentHistory(): Promise<RecentHistoryResponse> {
  const response = await api.get<RecentHistoryResponse>('/users/history')
  return response.data
}

export async function getWan22HistoryChain(taskId: string): Promise<Wan22HistoryChainResponse> {
  const response = await api.get<Wan22HistoryChainResponse>(`/users/history/${taskId}/wan22-chain`)
  return response.data
}

export async function stitchWan22HistoryChain(taskId: string): Promise<HistoryItem> {
  const response = await api.post<HistoryItem>(`/users/history/${taskId}/wan22-chain/stitch`)
  return response.data
}

export async function getLtxHistoryChain(taskId: string): Promise<LtxHistoryChainResponse> {
  const response = await api.get<LtxHistoryChainResponse>(`/users/history/${taskId}/ltx-chain`)
  return response.data
}

export async function stitchLtxHistoryChain(taskId: string): Promise<HistoryItem> {
  const response = await api.post<HistoryItem>(`/users/history/${taskId}/ltx-chain/stitch`)
  return response.data
}

export async function getMyLibraryPosts(
  params: MyLibraryPostsParams
): Promise<PaginatedGalleryResponse<GalleryPost>> {
  const { scope, page, size, taskType } = params

  if (scope === 'submissions') {
    const response = await api.get<PaginatedGalleryResponse<GalleryPost>>('/gallery/my-posts', {
      params: {
        page,
        size,
        task_type: taskType === 'all' ? undefined : taskType,
      },
    })
    return response.data
  }

  if (scope === 'prompt_templates') {
    const response = await api.get<PaginatedGalleryResponse<GalleryPost>>('/gallery/my-prompt-unlocks', {
      params: {
        page,
        size,
        task_type: taskType === 'all' ? undefined : taskType,
      },
    })
    return response.data
  }

  if (scope === 'favorite') {
    const response = await api.get<PaginatedGalleryResponse<GalleryPost>>('/users/my-favorites', {
      params: {
        page,
        size,
        task_type: taskType === 'all' ? undefined : taskType,
      },
    })
    return response.data
  }

  const response = await api.get<PaginatedGalleryResponse<GalleryPost>>('/gallery/my-favorites', {
    params: {
      page,
      size,
      filter_type: scope,
      task_type: taskType === 'all' ? undefined : taskType,
    },
  })
  return response.data
}

export async function unlockGalleryPrompt(postId: number): Promise<PromptUnlockResponse> {
  const response = await api.post<PromptUnlockResponse>(`/gallery/posts/${postId}/prompt-unlock`)
  return response.data
}

export async function reportGalleryPost(
  postId: number,
  reason: GalleryReportReason
): Promise<GalleryReportSubmitResponse> {
  const response = await api.post<GalleryReportSubmitResponse>(
    `/gallery/posts/${postId}/reports`,
    { reason }
  )
  return response.data
}

export async function getUnifiedApplyContext(params: {
  source: ApplyContextSource
  itemId: number | string
  signal?: AbortSignal
}): Promise<RawApplyContextResponse> {
  const response = await api.get<RawApplyContextResponse>(
    `/gallery/items/${params.itemId}/apply-context`,
    {
      params: {
        source: params.source,
      },
      signal: params.signal,
    }
  )
  return response.data
}

export async function getGalleryCommentsPage(params: {
  postId: number
  page: number
  size: number
}): Promise<GalleryCommentsPage> {
  try {
    const response = await api.get<GalleryCommentsPage>(`/gallery/posts/${params.postId}/comments`, {
      params: {
        page: params.page,
        size: params.size,
      },
    })
    return response.data
  } catch (error: any) {
    if (error?.response?.status === 404) {
      return {
        items: [],
        total: 0,
        page: params.page,
        size: params.size,
        pages: 0,
      }
    }
    throw error
  }
}
