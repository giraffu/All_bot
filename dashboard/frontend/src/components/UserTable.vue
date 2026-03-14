<script setup>
import { ref, computed } from 'vue'
import { EyeOutlined, EditOutlined, DeleteOutlined, UserDeleteOutlined } from '@ant-design/icons-vue'
import { formatDate } from '../utils/helpers'
import { updateUserCredits, clearUserHistory, deleteUser } from '../api/api'
import { message, Modal } from 'ant-design-vue'

const props = defineProps({
  users: {
    type: Array,
    required: true
  },
  loading: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: null
  }
})

const filteredUsers = computed(() => {
  return props.users || []
})

const emit = defineEmits(['viewHistory', 'refresh'])

// Credits editing state
const editCreditsVisible = ref(false)
const currentEditingUser = ref(null)
const newCreditsValue = ref(0)
const updatingCredits = ref(false)

const handleEditCredits = (record) => {
  currentEditingUser.value = record
  newCreditsValue.value = record.credits
  editCreditsVisible.value = true
}

const saveCredits = async () => {
  if (!currentEditingUser.value) return
  
  updatingCredits.value = true
  try {
    await updateUserCredits(currentEditingUser.value.id, newCreditsValue.value)
    message.success(`用户 ${currentEditingUser.value.id} 灵石已更新为 ${newCreditsValue.value}`)
    editCreditsVisible.value = false
    emit('refresh')
  } catch (err) {
    message.error('更新灵石失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    updatingCredits.value = false
  }
}

const handleClearHistory = (record) => {
  Modal.confirm({
    title: '确认清除数据？',
    content: `这将永久删除用户 ${record.full_name || record.id} 的所有历史记录（包括图片和Prompt），但会保留灵石和邀请信息。此操作不可撤销。`,
    okText: '确认清除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await clearUserHistory(record.id)
        message.success('用户历史数据已成功清除')
        emit('refresh')
      } catch (err) {
        message.error('清除数据失败: ' + (err.response?.data?.detail || err.message))
      }
    }
  })
}

const handleDeleteUser = (record) => {
  Modal.confirm({
    title: '确认彻底删除用户？',
    content: `这将从数据库中永久移除用户 ${record.full_name || record.id} 的所有信息（包括身份组、灵石、签到记录、生成历史等）。用户重新启动机器人后将作为全新的“凡人”身份加入。此操作不可撤销！`,
    okText: '确认彻底删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await deleteUser(record.id)
        message.success('用户及其所有关联数据已成功从数据库移除')
        emit('refresh')
      } catch (err) {
        message.error('删除用户失败: ' + (err.response?.data?.detail || err.message))
      }
    }
  })
}

const columns = [
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
    title: '邀请人',
    key: 'inviter',
    width: 150,
  },
  {
    title: '灵石',
    dataIndex: 'credits',
    key: 'credits',
    width: 100,
    sorter: (a, b) => a.credits - b.credits,
  },
  {
    title: '累计签到',
    dataIndex: 'checkin_count',
    key: 'checkin_count',
    width: 100,
    sorter: (a, b) => a.checkin_count - b.checkin_count,
  },
  {
    title: '邀请人数',
    dataIndex: 'referral_count',
    key: 'referral_count',
    width: 100,
    sorter: (a, b) => a.referral_count - b.referral_count,
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
    sorter: (a, b) => a.generation_count - b.generation_count,
  },
  {
    title: '累计贡献',
    dataIndex: 'total_contributions',
    key: 'total_contributions',
    width: 100,
    sorter: (a, b) => (a.total_contributions || 0) - (b.total_contributions || 0),
  },
  {
    title: '采纳次数',
    dataIndex: 'approved_contributions',
    key: 'approved_contributions',
    width: 100,
    sorter: (a, b) => (a.approved_contributions || 0) - (b.approved_contributions || 0),
  },
  {
    title: '注册时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 180,
    sorter: (a, b) => new Date(a.created_at) - new Date(b.created_at),
  },
  {
    title: '最新操作时间',
    dataIndex: 'last_activity',
    key: 'last_activity',
    width: 180,
    sorter: (a, b) => {
      const dateA = a.last_activity ? new Date(a.last_activity) : new Date(0);
      const dateB = b.last_activity ? new Date(b.last_activity) : new Date(0);
      return dateA - dateB;
    },
  },
  {
    title: '操作',
    key: 'action',
    fixed: 'right',
    width: 320,
  },
]
</script>

<template>
  <a-card title="用户列表" :bordered="false" class="shadow-sm rounded-xl h-full flex flex-col">
    <template #extra>
      <a-tag color="blue">总计: {{ filteredUsers.length }}</a-tag>
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
        :data-source="filteredUsers" 
        :loading="loading"
        :row-key="record => record.id"
        :pagination="{ 
          pageSize: 20,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          size: 'small'
        }"
        size="middle"
        :scroll="{ y: 'calc(100vh - 350px)', x: 1400 }"
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
          </div>
        </template>
        
        <template v-else-if="column.key === 'user_group'">
          <a-tag :color="record.user_group === '金丹期' ? 'gold' : record.user_group === '筑基期' ? 'purple' : record.user_group === '练气期' ? 'blue' : 'default'">
            {{ record.user_group || '凡人' }}
          </a-tag>
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

        <template v-else-if="column.key === 'channel_joined'">
          <a-tag :color="record.channel_joined ? 'green' : 'red'">
            {{ record.channel_joined ? '是' : '否' }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'generation_count'">
          <a-tag color="purple" class="font-bold">
            {{ record.generation_count }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'total_contributions'">
          <a-tag :color="(record.total_contributions || 0) > 0 ? 'blue' : 'default'">
            {{ record.total_contributions || 0 }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'approved_contributions'">
          <a-tag :color="(record.approved_contributions || 0) > 0 ? 'gold' : 'default'">
            {{ record.approved_contributions || 0 }}
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
          <div class="flex gap-2">
            <a-button 
              type="link" 
              size="small"
              @click="$emit('viewHistory', record)"
            >
              <template #icon><eye-outlined /></template>
              历史
            </a-button>

            <a-button 
              type="link" 
              size="small"
              @click="handleEditCredits(record)"
            >
              <template #icon><edit-outlined /></template>
              修改灵石
            </a-button>

            <a-button 
              type="link" 
              size="small"
              danger
              @click="handleClearHistory(record)"
            >
              <template #icon><delete-outlined /></template>
              清除数据
            </a-button>

            <a-button 
              type="link" 
              size="small"
              danger
              @click="handleDeleteUser(record)"
            >
              <template #icon><user-delete-outlined /></template>
              彻底删除
            </a-button>
          </div>
        </template>
      </template>
    </a-table>
    </div>

    <!-- Edit Credits Modal -->
    <a-modal
      v-model:visible="editCreditsVisible"
      title="修改用户灵石"
      @ok="saveCredits"
      :confirmLoading="updatingCredits"
      okText="保存"
      cancelText="取消"
    >
      <div class="py-4">
        <p class="mb-2 text-gray-500">正在为用户 <span class="font-bold text-gray-800">{{ currentEditingUser?.full_name || currentEditingUser?.id }}</span> 修改灵石</p>
        <div class="flex items-center gap-4">
          <span class="shrink-0">灵石数值:</span>
          <a-input-number v-model:value="newCreditsValue" :min="0" class="w-full" />
        </div>
        <p class="mt-4 text-xs text-amber-500 italic">* 增加灵石直接输入更大数值，减少灵石输入较小数值即可。</p>
      </div>
    </a-modal>
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
</style>
