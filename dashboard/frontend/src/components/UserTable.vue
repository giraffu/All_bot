<script setup>
import { computed } from 'vue'
import { formatDate } from '../utils/helpers'
import { useUserTableState } from '../composables/useUserTableState'
import UserTableToolbar from './UserTableToolbar.vue'
import UserTableRowActions from './UserTableRowActions.vue'
import UserTableDialogs from './UserTableDialogs.vue'
import UserTransferDialog from './UserTransferDialog.vue'
import { useDashboardViewport } from '../composables/useDashboardViewport'

const emit = defineEmits(['viewHistory', 'viewFavorites'])
const { isMobile } = useDashboardViewport()
const {
  users,
  loading,
  error,
  currentPage,
  pageSize,
  totalUsers,
  searchUserId,
  searchQuery,
  isQueryPartial,
  filterIdentity,
  filterUserGroup,
  filterSubmissionBanned,
  filterAlipayDirect,
  searchUsername,
  isUsernamePartial,
  sortBy,
  sortOrder,
  statsModalVisible,
  statsLoading,
  currentUserStats,
  currentUser,
  editCreditsVisible,
  currentEditingUser,
  newCreditsValue,
  newCheckinCountValue,
  updatingCredits,
  giftModalVisible,
  currentGiftUser,
  availablePlans,
  giftForm,
  giftingPlan,
  editIdentityVisible,
  currentIdentityUser,
  newIdentityValue,
  newExpireAtValue,
  autoConvertIdentity,
  updatingIdentity,
  editGroupVisible,
  updatingGroup,
  currentGroupUser,
  newGroupValue,
  editChannelMemberVisible,
  updatingChannelMember,
  currentChannelMemberUser,
  newChannelMemberValue,
  transferModalVisible,
  transferringData,
  transferSearchLoading,
  currentTransferSourceUser,
  transferTargetUserId,
  transferTargetKeyword,
  transferTargetOptions,
  transferConfirmText,
  transferNote,
  allIdentities,
  handleTableChange,
  onSearchInput,
  handleViewStats,
  handleEditCredits,
  saveCredits,
  handleClearHistory,
  handleDeleteUser,
  handleEditIdentity,
  handleEditGroup,
  handleEditChannelMember,
  handleToggleSubmissionBan,
  handleToggleAlipayDirect,
  saveIdentity,
  saveGroup,
  saveChannelMember,
  searchTransferTargets,
  handleTransferData,
  submitTransfer,
  handleGiftPlan,
  submitGift,
} = useUserTableState(formatDate)

const baseColumns = [
  {
    title: '#',
    key: 'index',
    width: 60,
    align: 'center',
  },
  {
    title: 'ID',
    dataIndex: 'id',
    key: 'id',
    width: 100,
    sorter: true,
  },
  {
    title: '用户信息',
    key: 'user_info',
    width: 150,
  },
  {
    title: '修为',
    dataIndex: 'user_group',
    key: 'user_group',
    width: 100,
    align: 'center',
  },
  {
    title: '身份组',
    dataIndex: 'current_identity',
    key: 'current_identity',
    width: 100,
    align: 'center',
  },
  {
    title: '身份到期时间',
    dataIndex: 'identity_expire_at',
    key: 'identity_expire_at',
    width: 160,
    align: 'center',
  },
  {
    title: '邀请人',
    key: 'inviter',
    width: 150,
  },
  {
    title: '灵石',
    dataIndex: 'credits',
    key: 'credits',
    width: 100,
    sorter: true,
  },
  {
    title: '累计签到',
    dataIndex: 'checkin_count',
    key: 'checkin_count',
    width: 100,
    sorter: true,
  },
  {
    title: '邀请人数',
    dataIndex: 'referral_count',
    key: 'referral_count',
    width: 100,
    sorter: true,
  },
  {
    title: '邀请折合(USDT)',
    dataIndex: 'invited_total_usdt',
    key: 'invited_total_usdt',
    width: 140,
    align: 'center',
  },
  {
    title: '已入宗门',
    key: 'channel_joined',
    width: 100,
    align: 'center',
  },
  {
    title: '总生成数',
    dataIndex: 'generation_count',
    key: 'generation_count',
    width: 100,
    sorter: true,
  },
  {
    title: '注册时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 180,
    sorter: true,
  },
  {
    title: '最新操作时间',
    dataIndex: 'last_activity',
    key: 'last_activity',
    width: 180,
    sorter: true,
  },
  {
    title: '操作',
    key: 'action',
    fixed: 'right',
    width: 320,
  },
]

const sortableColumnKeys = new Set([
  'id',
  'credits',
  'checkin_count',
  'referral_count',
  'generation_count',
  'created_at',
  'last_activity',
])

const columns = computed(() =>
  baseColumns.map(column => {
    const responsiveColumn = column.key === 'action'
      ? { ...column, width: isMobile.value ? 168 : column.width }
      : column
    if (!sortableColumnKeys.has(column.key)) {
      return responsiveColumn
    }
    const activeSortOrder =
      sortBy.value === column.key
        ? (sortOrder.value === 'asc' ? 'ascend' : 'descend')
        : null
    return {
      ...responsiveColumn,
      sortOrder: activeSortOrder,
    }
  })
)
</script>

<template>
  <a-card title="用户列表" :bordered="false" class="shadow-sm rounded-xl h-full flex flex-col">
    <template #extra>
      <user-table-toolbar
        v-model:filter-identity="filterIdentity"
        v-model:filter-user-group="filterUserGroup"
        v-model:filter-submission-banned="filterSubmissionBanned"
        v-model:filter-alipay-direct="filterAlipayDirect"
        v-model:search-user-id="searchUserId"
        v-model:search-username="searchUsername"
        v-model:is-username-partial="isUsernamePartial"
        v-model:search-query="searchQuery"
        v-model:is-query-partial="isQueryPartial"
        :total-users="totalUsers"
        @search="onSearchInput"
      />
    </template>
    
    <a-alert
      v-if="error"
      :message="error"
      type="error"
      show-icon
      class="mb-4"
    />

    <div class="flex-1 overflow-hidden relative min-h-0">
      <a-table 
        :columns="columns" 
        :data-source="users" 
        :loading="loading"
        :row-key="record => record.id"
        :pagination="{ 
          current: currentPage,
          pageSize: pageSize,
          total: totalUsers,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          size: 'small'
        }"
        @change="handleTableChange"
        size="middle"
        :scroll="{ y: isMobile ? 'calc(100dvh - 410px)' : 'calc(100vh - 350px)', x: isMobile ? 1388 : 1540 }"
        class="ant-table-striped"
      >
      <template #bodyCell="{ column, record, index }">
        <template v-if="column.key === 'index'">
          <span class="text-gray-400 font-mono">{{ index + 1 }}</span>
        </template>
        
        <template v-else-if="column.key === 'user_info'">
          <div class="flex flex-col">
            <span class="font-medium text-gray-800">{{ record.full_name || '未知用户' }}</span>
            <span class="text-xs text-blue-500">@{{ record.username || 'n/a' }}</span>
            <a-tag v-if="record.is_submission_banned" color="red" class="mt-1 w-fit">
              投稿封禁
            </a-tag>
            <a-tag v-if="record.alipay_direct_enabled" color="blue" class="mt-1 w-fit">
              支付宝直连
            </a-tag>
          </div>
        </template>
        
        <template v-else-if="column.key === 'user_group'">
          <a-tag :color="record.user_group === '金丹期' ? 'gold' : record.user_group === '筑基期' ? 'purple' : record.user_group === '练气期' ? 'blue' : 'default'">
            {{ record.user_group || '凡人' }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'current_identity'">
          <a-tag :color="record.current_identity === '真传弟子' ? 'red' : record.current_identity === '核心弟子' ? 'orange' : record.current_identity === '内门弟子' ? 'cyan' : 'default'">
            {{ record.current_identity || '外门弟子' }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'identity_expire_at'">
          <span v-if="record.current_identity && record.current_identity !== '外门弟子' && record.identity_expire_at" 
                class="text-sm" 
                :class="new Date(record.identity_expire_at) < new Date() ? 'text-red-500' : 'text-green-600'">
            {{ formatDate(record.identity_expire_at) }}
          </span>
          <span v-else class="text-gray-400 text-sm">-</span>
        </template>

        <template v-else-if="column.key === 'inviter'">
          <div class="flex flex-col" v-if="record.inviter_info">
            <span class="font-medium text-gray-800">{{ record.inviter_info.full_name || record.inviter_info.id }}</span>
            <span class="text-xs text-blue-500" v-if="record.inviter_info.username">@{{ record.inviter_info.username }}</span>
          </div>
          <span v-else class="text-gray-400 text-sm">无</span>
        </template>
        
        <template v-else-if="column.key === 'credits'">
          <a-tag color="blue" class="font-bold">
            {{ record.credits }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'checkin_count'">
          <a-tag :color="record.checkin_count > 10 ? 'orange' : record.checkin_count > 0 ? 'cyan' : 'default'">
            {{ record.checkin_count }} 次
          </a-tag>
        </template>

        <template v-else-if="column.key === 'referral_count'">
          <a-tag :color="record.referral_count > 0 ? 'green' : 'default'">
            {{ record.referral_count }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'invited_total_usdt'">
          <span class="font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded border border-emerald-100">
            $ {{ Number(record.invited_total_usdt || 0).toFixed(2) }}
          </span>
        </template>

        <template v-else-if="column.key === 'channel_joined'">
          <a-tag :color="record.is_channel_member ? 'green' : 'red'">
            {{ record.is_channel_member ? '是' : '否' }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'generation_count'">
          <a-tag color="purple" class="font-bold">
            {{ record.generation_count }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'created_at'">
          <span class="text-gray-500 text-sm">
            {{ formatDate(record.created_at) }}
          </span>
        </template>

        <template v-else-if="column.key === 'last_activity'">
          <span class="text-sm" :class="record.last_activity ? 'text-blue-600' : 'text-gray-400'">
            {{ record.last_activity ? formatDate(record.last_activity) : '暂无操作' }}
          </span>
        </template>

        <template v-else-if="column.key === 'last_checkin'">
          <span class="text-gray-500 text-sm">
            {{ record.last_checkin || '从未签到' }}
          </span>
        </template>

        <template v-else-if="column.key === 'action'">
          <user-table-row-actions
            :record="record"
            @view-stats="handleViewStats"
            @gift-plan="handleGiftPlan"
            @view-history="$emit('viewHistory', $event)"
            @view-favorites="$emit('viewFavorites', $event)"
            @edit-identity="handleEditIdentity"
            @edit-group="handleEditGroup"
            @edit-channel-member="handleEditChannelMember"
            @toggle-submission-ban="handleToggleSubmissionBan"
            @toggle-alipay-direct="handleToggleAlipayDirect"
            @edit-credits="handleEditCredits"
            @transfer-data="handleTransferData"
            @clear-history="handleClearHistory"
            @delete-user="handleDeleteUser"
          />
        </template>
      </template>
    </a-table>
    </div>

    <user-table-dialogs
      :format-date="formatDate"
      :all-identities="allIdentities"
      v-model:edit-identity-visible="editIdentityVisible"
      v-model:new-identity-value="newIdentityValue"
      v-model:new-expire-at-value="newExpireAtValue"
      v-model:auto-convert-identity="autoConvertIdentity"
      :updating-identity="updatingIdentity"
      :current-identity-user="currentIdentityUser"
      @save-identity="saveIdentity"
      v-model:edit-group-visible="editGroupVisible"
      v-model:new-group-value="newGroupValue"
      :updating-group="updatingGroup"
      :current-group-user="currentGroupUser"
      @save-group="saveGroup"
      v-model:edit-channel-member-visible="editChannelMemberVisible"
      v-model:new-channel-member-value="newChannelMemberValue"
      :updating-channel-member="updatingChannelMember"
      :current-channel-member-user="currentChannelMemberUser"
      @save-channel-member="saveChannelMember"
      v-model:edit-credits-visible="editCreditsVisible"
      v-model:new-credits-value="newCreditsValue"
      v-model:new-checkin-count-value="newCheckinCountValue"
      :updating-credits="updatingCredits"
      :current-editing-user="currentEditingUser"
      @save-credits="saveCredits"
      v-model:gift-modal-visible="giftModalVisible"
      :gifting-plan="giftingPlan"
      :current-gift-user="currentGiftUser"
      :available-plans="availablePlans"
      :gift-form="giftForm"
      @update:gift-form="giftForm = $event"
      @submit-gift="submitGift"
      v-model:stats-modal-visible="statsModalVisible"
      :stats-loading="statsLoading"
      :current-user-stats="currentUserStats"
      :current-user="currentUser"
    />

    <user-transfer-dialog
      v-model:visible="transferModalVisible"
      v-model:target-user-id="transferTargetUserId"
      v-model:confirm-text="transferConfirmText"
      v-model:note="transferNote"
      :loading="transferringData"
      :search-loading="transferSearchLoading"
      :source-user="currentTransferSourceUser"
      :target-options="transferTargetOptions"
      @search-targets="searchTransferTargets"
      @submit="submitTransfer"
    />
  </a-card>
</template>

<style scoped>
:deep(.ant-table-wrapper) {
  height: 100%;
}
:deep(.ant-spin-nested-loading) {
  height: 100%;
}
:deep(.ant-spin-container) {
  height: 100%;
  display: flex;
  flex-direction: column;
}
:deep(.ant-table) {
  flex: 1;
  overflow: hidden;
  background: transparent;
}
:deep(.ant-card-head) {
  border-bottom: 1px solid #f0f0f0;
  padding: 0 24px;
}
:deep(.ant-card-body) {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 16px 24px 24px 24px;
}
:deep(.ant-table-pagination.ant-pagination) {
  margin: 16px 0 0 0;
}

@media (max-width: 767px) {
  :deep(.ant-card-head) {
    padding: 0 12px;
  }

  :deep(.ant-card-body) {
    padding: 12px;
  }

  :deep(.ant-table-cell-fix-right) {
    box-shadow: -4px 0 10px rgba(15, 23, 42, 0.08);
  }
}
</style>
