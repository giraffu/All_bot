import api from '@/api'
import type {
  FollowActionResponse,
  FollowingListResponse,
  PublicUserProfileResponse,
} from '@/types/social'

export async function getMyFollowing(): Promise<FollowingListResponse> {
  const response = await api.get<FollowingListResponse>('/users/me/follows')
  return response.data
}

export async function getPublicUserProfile(userId: number): Promise<PublicUserProfileResponse> {
  const response = await api.get<PublicUserProfileResponse>(`/users/${userId}/public-profile`)
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
