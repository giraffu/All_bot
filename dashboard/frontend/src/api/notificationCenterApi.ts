import { api, appendQueryParam, unwrapData, withQuery } from './client'

export interface NotificationCenterSettings {
  admin_telegram_user_ids: number[]
  authorized_group_ids: number[]
  support_ticket_user_ids: number[]
  queue_alerts_enabled: boolean
  group_collection_enabled: boolean
  daily_reports_enabled: boolean
  weekly_reports_enabled: boolean
  monthly_reports_enabled: boolean
}

export interface ObserverReportRecord {
  run_key: string
  report_type: string
  period_start: string
  period_end: string
  status: string
  attempts: number
  model_id?: string | null
  content?: string | null
  error?: string | null
  completed_at?: string | null
  updated_at: string
}

export interface ObserverNotificationRecord {
  id: number
  event_type: string
  destination_chat_id?: number | null
  status: string
  content_preview: string
  error_type?: string | null
  created_at: string
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export const fetchNotificationCenterSettings = async (): Promise<NotificationCenterSettings> =>
  api.get('/api/notification-center/settings').then(unwrapData)

export const updateNotificationCenterSettings = async (
  payload: NotificationCenterSettings,
): Promise<NotificationCenterSettings> =>
  api.put('/api/notification-center/settings', payload).then(unwrapData)

const recordsUrl = (path: string, page: number, pageSize: number) =>
  withQuery(path, (params: URLSearchParams) => {
    appendQueryParam(params, 'page', page)
    appendQueryParam(params, 'page_size', pageSize)
  })

export const fetchObserverReports = async (
  page = 1,
  pageSize = 20,
): Promise<Paginated<ObserverReportRecord>> =>
  api.get(recordsUrl('/api/notification-center/reports', page, pageSize)).then(unwrapData)

export const fetchObserverNotificationLogs = async (
  page = 1,
  pageSize = 20,
): Promise<Paginated<ObserverNotificationRecord>> =>
  api.get(recordsUrl('/api/notification-center/notifications', page, pageSize)).then(unwrapData)
