import { defineAsyncComponent, markRaw, type Component } from 'vue'
import {
  AppstoreOutlined,
  BankOutlined,
  MessageOutlined,
  MenuOutlined,
  DashboardOutlined,
  FileTextOutlined,
  GiftOutlined,
  HistoryOutlined,
  HomeOutlined,
  NotificationOutlined,
  PayCircleOutlined,
  PictureOutlined,
  RobotOutlined,
  UserOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'

export type DashboardTabKey =
  | 'home'
  | 'finance'
  | 'monitor'
  | 'users'
  | 'history'
  | 'worker_history'
  | 'logs'
  | 'paid_group_guard'
  | 'group_manage'
  | 'main_bot_menu'
  | 'recharge'
  | 'templates'
  | 'gallery'
  | 'gallery_comments'
  | 'gallery_reports'
  | 'referrals'
  | 'site_notice'
  | 'support_tickets'
  | 'reference_assets'
  | 'prompt_optimizer'

export interface DashboardTabConfig {
  key: DashboardTabKey
  label: string
  icon: Component
  component: Component
  containerClass: string
  scrollable: boolean
}

export const BASE_CONTAINER_CLASS = 'flex-1 flex flex-col min-h-0'
export const PANEL_CONTAINER_CLASS =
  'dashboard-panel flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0 min-w-0'

export const defaultDashboardTabKey: DashboardTabKey = 'templates'

export const dashboardTabs: DashboardTabConfig[] = [
  {
    key: 'home',
    label: '数据大盘',
    icon: HomeOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/HomeDashboard.vue'))),
    containerClass: BASE_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'finance',
    label: '充值数据',
    icon: BankOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/FinanceDashboard.vue'))),
    containerClass: BASE_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'monitor',
    label: '系统监控',
    icon: DashboardOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/DashboardMonitorView.vue'))),
    containerClass: `${BASE_CONTAINER_CLASS} gap-6`,
    scrollable: true,
  },
  {
    key: 'users',
    label: '用户管理',
    icon: UserOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/UserTable.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: false,
  },
  {
    key: 'history',
    label: '历史生成',
    icon: HistoryOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/HistoryTable.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: false,
  },
  {
    key: 'worker_history',
    label: 'Worker记录',
    icon: RobotOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/WorkerHistoryTable.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: false,
  },
  {
    key: 'logs',
    label: '操作日志',
    icon: FileTextOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/LogTable.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'paid_group_guard',
    label: '群审核Bot',
    icon: RobotOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/PaidGroupGuardSettings.vue'))),
    containerClass: BASE_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'group_manage',
    label: '群管理Bot',
    icon: RobotOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/GroupManageSettings.vue'))),
    containerClass: BASE_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'main_bot_menu',
    label: '主Bot菜单',
    icon: MenuOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/MainBotMenuSettings.vue'))),
    containerClass: BASE_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'recharge',
    label: '充值系统',
    icon: PayCircleOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/RechargeSystem.vue'))),
    containerClass: BASE_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'templates',
    label: '模板共建',
    icon: PictureOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/TemplateManager.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'reference_assets',
    label: '官方素材库',
    icon: PictureOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/ReferenceAssetManager.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'prompt_optimizer',
    label: '提示词优化配置',
    icon: RobotOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/PromptOptimizerConfigManager.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'gallery',
    label: '广场内容管理',
    icon: AppstoreOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/GalleryTable.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: false,
  },
  {
    key: 'gallery_comments',
    label: '评论管理',
    icon: MessageOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/GalleryCommentsTable.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: false,
  },
  {
    key: 'gallery_reports',
    label: '举报管理',
    icon: WarningOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/GalleryReportsTable.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: false,
  },
  {
    key: 'referrals',
    label: '邀请奖励',
    icon: GiftOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/ReferralTable.vue'))),
    containerClass: BASE_CONTAINER_CLASS,
    scrollable: true,
  },
  {
    key: 'support_tickets',
    label: '客服工单',
    icon: MessageOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/SupportTickets.vue'))),
    containerClass: PANEL_CONTAINER_CLASS,
    scrollable: false,
  },
  {
    key: 'site_notice',
    label: '站点通知',
    icon: NotificationOutlined,
    component: markRaw(defineAsyncComponent(() => import('../components/SiteNoticeSettings.vue'))),
    containerClass: BASE_CONTAINER_CLASS,
    scrollable: true,
  },
]

export const dashboardTabMap = Object.fromEntries(
  dashboardTabs.map(tab => [tab.key, tab]),
) as Record<DashboardTabKey, DashboardTabConfig>

export const scrollableDashboardTabKeys = dashboardTabs
  .filter(tab => tab.scrollable)
  .map(tab => tab.key)
