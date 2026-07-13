import api from '@/api'
import type {
  FollowActionResponse,
  FollowersListResponse,
  FollowingListResponse,
  PublicUserProfileResponse,
  UserSearchResponse,
} from '@/types/social'

interface PublicUserProfileParams {
  page?: number
  size?: number
}

interface SearchUsersParams {
  q: string
  limit?: number
}

export async function getMyFollowing(): Promise<FollowingListResponse> {
  const response = await api.get<FollowingListResponse>('/users/me/follows')
  return response.data
}

export async function getMyFollowers(): Promise<FollowersListResponse> {
  const response = await api.get<FollowersListResponse>('/users/me/followers')
  return response.data
}

export async function searchUsers(params: SearchUsersParams): Promise<UserSearchResponse> {
  const response = await api.get<UserSearchResponse>('/users/search', { params })
  return response.data
}

export async function getPublicUserProfile(
  userId: number,
  params: PublicUserProfileParams = {},
): Promise<PublicUserProfileResponse> {
  const response = await api.get<PublicUserProfileResponse>(
    `/users/${userId}/public-profile`,
    { params },
  )
  return response.data
}

export async function followUser(userId: number): Promise<FollowActionResponse> {
  const response = await api.post<FollowActionResponse>(`/users/${userId}/follow`)
  return response.data
}

export async function unfollowUser(userId: number): Promise<FollowActionResponse> {
  const response = await api.delete<FollowActionResponse>(`/users/${userId}/follow`)
  return response.data
}
