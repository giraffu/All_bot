<script setup>
import {
  EyeOutlined,
  EditOutlined,
  DeleteOutlined,
  UserDeleteOutlined,
  UserOutlined,
  GiftOutlined,
  SafetyCertificateOutlined,
  InfoCircleOutlined,
  TeamOutlined,
  DownOutlined,
  BookOutlined,
  SwapOutlined,
  StopOutlined,
  UnlockOutlined,
  DollarCircleOutlined,
} from '@ant-design/icons-vue'

defineProps({
  record: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits([
  'view-stats',
  'gift-plan',
  'view-history',
  'view-favorites',
  'edit-identity',
  'edit-group',
  'edit-channel-member',
  'toggle-submission-ban',
  'toggle-alipay-direct',
  'edit-credits',
  'transfer-data',
  'clear-history',
  'delete-user',
])
</script>

<template>
  <div class="flex flex-wrap gap-2">
    <a-button type="link" size="small" @click="emit('view-stats', record)">
      <template #icon><info-circle-outlined /></template>
      详细信息
    </a-button>

    <a-button type="link" size="small" @click="emit('gift-plan', record)">
      <template #icon><gift-outlined /></template>
      赠送套餐
    </a-button>

    <a-button type="link" size="small" @click="emit('view-history', record)">
      <template #icon><eye-outlined /></template>
      历史
    </a-button>

    <a-button type="link" size="small" @click="emit('view-favorites', record)">
      <template #icon><book-outlined /></template>
      收藏
    </a-button>

    <a-dropdown :trigger="['click']">
      <a-button type="link" size="small" @click.prevent>
        更多 <down-outlined />
      </a-button>
      <template #overlay>
        <a-menu>
          <a-menu-item key="identity">
            <a-button type="text" size="small" class="w-full text-left" @click="emit('edit-identity', record)">
              <template #icon><safety-certificate-outlined /></template>
              切换身份
            </a-button>
          </a-menu-item>
          <a-menu-item key="group">
            <a-button type="text" size="small" class="w-full text-left" @click="emit('edit-group', record)">
              <template #icon><user-outlined /></template>
              切换修为
            </a-button>
          </a-menu-item>
          <a-menu-item key="channel">
            <a-button type="text" size="small" class="w-full text-left" @click="emit('edit-channel-member', record)">
              <template #icon><team-outlined /></template>
              入宗状态
            </a-button>
          </a-menu-item>
          <a-menu-item key="submission-ban">
            <a-button
              type="text"
              size="small"
              class="w-full text-left"
              :danger="!record.is_submission_banned"
              @click="emit('toggle-submission-ban', record)"
            >
              <template #icon>
                <stop-outlined v-if="!record.is_submission_banned" />
                <unlock-outlined v-else />
              </template>
              {{ record.is_submission_banned ? '解除投稿封禁' : '禁止投稿' }}
            </a-button>
          </a-menu-item>
          <a-menu-item key="alipay-direct">
            <a-button
              type="text"
              size="small"
              class="w-full text-left"
              :danger="record.alipay_direct_enabled"
              @click="emit('toggle-alipay-direct', record)"
            >
              <template #icon><dollar-circle-outlined /></template>
              {{ record.alipay_direct_enabled ? '关闭支付宝直连' : '开启支付宝直连' }}
            </a-button>
          </a-menu-item>
          <a-menu-item key="credits">
            <a-button type="text" size="small" class="w-full text-left" @click="emit('edit-credits', record)">
              <template #icon><edit-outlined /></template>
              修改数据
            </a-button>
          </a-menu-item>
          <a-menu-item key="transfer">
            <a-button type="text" size="small" danger class="w-full text-left" @click="emit('transfer-data', record)">
              <template #icon><swap-outlined /></template>
              转移数据
            </a-button>
          </a-menu-item>
          <a-menu-item key="clear">
            <a-button type="text" size="small" danger class="w-full text-left" @click="emit('clear-history', record)">
              <template #icon><delete-outlined /></template>
              清除数据
            </a-button>
          </a-menu-item>
          <a-menu-item key="delete">
            <a-button type="text" size="small" danger class="w-full text-left" @click="emit('delete-user', record)">
              <template #icon><user-delete-outlined /></template>
              彻底删除
            </a-button>
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>
  </div>
</template>
