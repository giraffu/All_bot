import { computed } from 'vue'
import {
  AppstoreOutlined,
  BankOutlined,
  MessageOutlined,
  DashboardOutlined,
  FileTextOutlined,
  GiftOutlined,
  HistoryOutlined,
  HomeOutlined,
  LogoutOutlined,
  NotificationOutlined,
  PayCircleOutlined,
  PictureOutlined,
  RobotOutlined,
  UserOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'

export function useDashboardNavigation(activeTab: { value: string[] }) {
  const menuItems = [
    { key: 'home', label: '数据大盘', icon: HomeOutlined },
    { key: 'finance', label: '充值数据', icon: BankOutlined },
    { key: 'monitor', label: '系统监控', icon: DashboardOutlined },
    { key: 'users', label: '用户管理', icon: UserOutlined },
    { key: 'history', label: '历史生成', icon: HistoryOutlined },
    { key: 'worker_history', label: 'Worker记录', icon: RobotOutlined },
    { key: 'logs', label: '操作日志', icon: FileTextOutlined },
    { key: 'paid_group_guard', label: '群审核Bot', icon: RobotOutlined },
    { key: 'recharge', label: '充值系统', icon: PayCircleOutlined },
    { key: 'templates', label: '模板共建', icon: PictureOutlined },
    { key: 'gallery', label: '广场内容管理', icon: AppstoreOutlined },
    { key: 'gallery_comments', label: '评论管理', icon: MessageOutlined },
    { key: 'gallery_reports', label: '举报管理', icon: WarningOutlined },
    { key: 'referrals', label: '邀请奖励', icon: GiftOutlined },
    { key: 'site_notice', label: '站点通知', icon: NotificationOutlined },
  ]

  const scrollableTabKeys = [
    'home',
    'finance',
    'monitor',
    'templates',
    'logs',
    'paid_group_guard',
    'recharge',
    'referrals',
    'site_notice',
  ]

  const currentTabTitle = computed(() => {
    const matched = menuItems.find((item) => item.key === activeTab.value[0])
    return matched?.label || '模板共建'
  })

  return {
    menuItems,
    scrollableTabKeys,
    currentTabTitle,
    logoutIcon: LogoutOutlined,
  }
}
