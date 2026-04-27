<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { EyeOutlined, EditOutlined, DeleteOutlined, UserDeleteOutlined, SearchOutlined, GiftOutlined, SafetyCertificateOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import { formatDate } from '../utils/helpers'
import { updateUserCredits, clearUserHistory, deleteUser, fetchPlans, adminGiftPlan, updateUserIdentity, fetchUsers, fetchUserStats } from '../api/api'
import { message, Modal } from 'ant-design-vue'

const emit = defineEmits(['viewHistory'])

// State
const users = ref([])
const loading = ref(false)
const error = ref(null)

// Pagination & Search
const currentPage = ref(1)
const pageSize = ref(20)
const totalUsers = ref(0)
const searchQuery = ref('')
const searchTimeout = ref(null)

const loadUsersData = async () => {
  loading.value = true
  error.value = null
  try {
    const res = await fetchUsers(currentPage.value, pageSize.value, searchQuery.value)
    users.value = res.items || []
    totalUsers.value = res.total || 0
  } catch (err) {
    console.error('Failed to load users:', err)
    error.value = '加载用户列表失败'
  } finally {
    loading.value = false
  }
}

const handleTableChange = (pagination) => {
  currentPage.value = pagination.current
  pageSize.value = pagination.pageSize
  loadUsersData()
}

const onSearchInput = () => {
  if (searchTimeout.value) clearTimeout(searchTimeout.value)
  searchTimeout.value = setTimeout(() => {
    currentPage.value = 1
    loadUsersData()
  }, 500)
}

// User Stats Modal
const statsModalVisible = ref(false)
const statsLoading = ref(false)
const currentUserStats = ref(null)
const currentUser = ref(null)

const handleViewStats = async (record) => {
  currentUser.value = record
  statsModalVisible.value = true
  statsLoading.value = true
  currentUserStats.value = null
  try {
    currentUserStats.value = await fetchUserStats(record.id)
  } catch (err) {
    message.error('获取统计数据失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    statsLoading.value = false
  }
}

// Credits editing state
const editCreditsVisible = ref(false)
const currentEditingUser = ref(null)
const newCreditsValue = ref(0)
const newCheckinCountValue = ref(0)
const updatingCredits = ref(false)

const handleEditCredits = (record) => {
  currentEditingUser.value = record
  newCreditsValue.value = record.credits
  newCheckinCountValue.value = record.checkin_count || 0
  editCreditsVisible.value = true
}

const saveCredits = async () => {
  if (!currentEditingUser.value) return
  
  updatingCredits.value = true
  try {
    await updateUserCredits(
      currentEditingUser.value.id, 
      newCreditsValue.value,
      newCheckinCountValue.value
    )
    message.success(`用户 ${currentEditingUser.value.id} 数据已更新`)
    editCreditsVisible.value = false
    loadUsersData()
  } catch (err) {
    message.error('更新失败: ' + (err.response?.data?.detail || err.message))
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
        loadUsersData()
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
        loadUsersData()
      } catch (err) {
        message.error('删除用户失败: ' + (err.response?.data?.detail || err.message))
      }
    }
  })
}

// Gift state
const giftModalVisible = ref(false)
const currentGiftUser = ref(null)
const availablePlans = ref([])
const giftForm = ref({
  plan_id: null,
  note: '后台手动赠送'
})
const giftingPlan = ref(false)

// Identity editing state
const editIdentityVisible = ref(false)
const currentIdentityUser = ref(null)
const newIdentityValue = ref('')
const newExpireAtValue = ref(null)
const autoConvertIdentity = ref(true)
const updatingIdentity = ref(false)

const allIdentities = [
  '外门弟子',
  '内门弟子',
  '核心弟子',
  '真传弟子'
]

const handleEditIdentity = (record) => {
  currentIdentityUser.value = record
  newIdentityValue.value = record.current_identity || '外门弟子'
  newExpireAtValue.value = null // Start as null to allow auto-conversion
  autoConvertIdentity.value = true
  editIdentityVisible.value = true
}

const saveIdentity = async () => {
  if (!currentIdentityUser.value) return
  
  updatingIdentity.value = true
  try {
    const res = await updateUserIdentity(
      currentIdentityUser.value.id,
      newIdentityValue.value,
      newExpireAtValue.value,
      autoConvertIdentity.value
    )
    const newExpireStr = res.identity_expire_at ? formatDate(res.identity_expire_at) : '永不过期'
    message.success(`用户 ${currentIdentityUser.value.id} 身份已更新为 ${res.current_identity}，到期时间：${newExpireStr}`)
    editIdentityVisible.value = false
    loadUsersData()
  } catch (err) {
    message.error('更新失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    updatingIdentity.value = false
  }
}

const loadPlans = async () => {
  try {
    const res = await fetchPlans()
    availablePlans.value = res.filter(p => p.is_active)
  } catch (err) {
    console.error('Failed to load plans:', err)
  }
}

const handleGiftPlan = (record) => {
  currentGiftUser.value = record
  // Refresh plans just in case
  giftForm.value = {
    plan_id: availablePlans.value.length > 0 ? availablePlans.value[0].id : null,
    note: '后台手动赠送'
  }
  giftModalVisible.value = true
}

const submitGift = async () => {
  if (!giftForm.value.plan_id) {
    message.warning('请选择一个套餐')
    return
  }
  
  giftingPlan.value = true
  try {
    await adminGiftPlan(currentGiftUser.value.id, giftForm.value.plan_id, giftForm.value.note)
    message.success(`成功为用户 ${currentGiftUser.value.id} 赠送套餐`)
    giftModalVisible.value = false
    loadUsersData()
  } catch (err) {
    message.error('赠送套餐失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    giftingPlan.value = false
  }
}

onMounted(() => {
  loadPlans()
  loadUsersData()
})

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
      <div class="flex items-center gap-4">
        <a-input
          v-model:value="searchQuery"
          @input="onSearchInput"
          placeholder="搜索用户名称/用户名"
          allow-clear
          class="w-64"
        >
          <template #prefix>
            <search-outlined class="text-gray-400"/>
          </template>
        </a-input>
        <a-tag color="blue">总计: {{ totalUsers }}</a-tag>
      </div>
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
              @click="handleViewStats(record)"
            >
              <template #icon><info-circle-outlined /></template>
              详细信息
            </a-button>

            <a-button 
              type="link" 
              size="small"
              @click="handleGiftPlan(record)"
            >
              <template #icon><gift-outlined /></template>
              赠送套餐
            </a-button>

            <a-button 
              type="link" 
              size="small"
              @click="handleEditIdentity(record)"
            >
              <template #icon><safety-certificate-outlined /></template>
              切换身份
            </a-button>

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
              修改数据
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

    <!-- Edit Identity Modal -->
    <a-modal
      v-model:visible="editIdentityVisible"
      title="切换用户身份组"
      @ok="saveIdentity"
      :confirmLoading="updatingIdentity"
      okText="确认切换"
      cancelText="取消"
    >
      <div class="py-4">
        <p class="mb-4 text-gray-500">正在修改用户 <span class="font-bold text-gray-800">{{ currentIdentityUser?.full_name || currentIdentityUser?.id }}</span> 的身份等级</p>
        <a-form layout="vertical">
          <a-form-item label="身份组等级" required>
            <a-select v-model:value="newIdentityValue" placeholder="请选择身份组">
              <a-select-option v-for="idnt in allIdentities" :key="idnt" :value="idnt">
                {{ idnt }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="到期时间">
            <a-date-picker 
              v-model:value="newExpireAtValue" 
              show-time 
              value-format="YYYY-MM-DD HH:mm:ss" 
              placeholder="选择到期时间（留空则不修改）" 
              class="w-full"
            />
          </a-form-item>
          <a-form-item v-if="!newExpireAtValue">
            <a-checkbox v-model:checked="autoConvertIdentity">
              自动折算剩余时长 (根据身份价值比例缩放时间)
            </a-checkbox>
          </a-form-item>
        </a-form>
        <div class="mt-4 p-3 bg-amber-50 text-amber-700 text-xs rounded border border-amber-100">
          <p class="font-bold mb-1">注意：</p>
          <ul class="list-disc pl-4 m-0 space-y-1">
            <li>手动切换身份不会赠送灵石。</li>
            <li>如果只需要补发灵石和套餐，请使用“赠送套餐”功能。</li>
            <li>此操作会记录管理员操作日志。</li>
          </ul>
        </div>
      </div>
    </a-modal>

    <!-- Edit Credits Modal -->
    <a-modal
      v-model:visible="editCreditsVisible"
      title="修改用户数据"
      @ok="saveCredits"
      :confirmLoading="updatingCredits"
      okText="保存"
      cancelText="取消"
    >
      <div class="py-4">
        <p class="mb-4 text-gray-500">正在为用户 <span class="font-bold text-gray-800">{{ currentEditingUser?.full_name || currentEditingUser?.id }}</span> 修改数据</p>
        <a-form layout="vertical">
          <a-form-item label="永久灵石余额">
            <a-input-number v-model:value="newCreditsValue" :min="0" class="w-full" />
          </a-form-item>
          <a-form-item label="累计签到次数">
            <a-input-number v-model:value="newCheckinCountValue" :min="0" class="w-full" />
          </a-form-item>
        </a-form>
        <p class="mt-2 text-xs text-amber-500 italic">* 增加数值直接输入更大数值，减少数值输入较小数值即可。</p>
      </div>
    </a-modal>

    <!-- Gift Plan Modal -->
    <a-modal
      v-model:visible="giftModalVisible"
      title="赠送/补发套餐"
      @ok="submitGift"
      :confirmLoading="giftingPlan"
      okText="确认赠送"
      cancelText="取消"
    >
      <div class="py-4">
        <p class="mb-4 text-gray-500">正在为用户 <span class="font-bold text-gray-800">{{ currentGiftUser?.full_name || currentGiftUser?.id }}</span> 发放权益</p>
        <a-form layout="vertical">
          <a-form-item label="选择套餐" required>
            <a-select v-model:value="giftForm.plan_id" placeholder="请选择要赠送的套餐">
              <a-select-option v-for="plan in availablePlans" :key="plan.id" :value="plan.id">
                {{ plan.name }} (送 {{ plan.reward_credits }} 灵石 / 境界: {{ plan.identity_name }})
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="操作备注" required>
            <a-input v-model:value="giftForm.note" placeholder="例如: 客诉补偿 / 内部赠送" />
          </a-form-item>
        </a-form>
        <div class="mt-4 p-3 bg-blue-50 text-blue-700 text-xs rounded border border-blue-100">
          <p class="font-bold mb-1">提示：</p>
          <ul class="list-disc pl-4 m-0 space-y-1">
            <li>赠送操作会生成一笔金额为 0 的充值订单用于对账。</li>
            <li>会正常下发该套餐包含的灵石、更新身份组并延长身份有效期。</li>
          </ul>
        </div>
      </div>
    </a-modal>
    <!-- Stats Modal -->
    <a-modal
      v-model:visible="statsModalVisible"
      title="用户详细统计"
      :footer="null"
      width="600px"
    >
      <div v-if="statsLoading" class="flex justify-center items-center h-48">
        <a-spin size="large" tip="加载数据中..." />
      </div>
      <div v-else-if="currentUserStats" class="py-4">
        <div class="mb-6 flex items-center gap-4">
          <a-avatar size="large" style="background-color: #1890ff">
            <template #icon><user-outlined /></template>
          </a-avatar>
          <div>
            <h3 class="text-lg font-bold m-0">{{ currentUser?.full_name || '未知用户' }}</h3>
            <div class="text-gray-500 text-sm">@{{ currentUser?.username || 'n/a' }} | ID: {{ currentUser?.id }}</div>
          </div>
        </div>

        <h4 class="text-md font-semibold text-gray-700 mb-3 border-b pb-2">历史充值统计</h4>
        <div class="grid grid-cols-3 gap-4 mb-6">
          <a-statistic title="充值 (RMB)" :value="currentUserStats.total_recharge_rmb" :precision="2" prefix="¥">
            <template #formatter="{ value }">
              <span class="text-red-600 font-bold font-mono">{{ value }}</span>
            </template>
          </a-statistic>
          <a-statistic title="充值 (TON)" :value="currentUserStats.total_recharge_ton" :precision="2">
            <template #formatter="{ value }">
              <span class="text-green-600 font-bold font-mono">{{ value }}</span>
            </template>
          </a-statistic>
          <a-statistic title="充值 (Stars)" :value="currentUserStats.total_recharge_stars">
            <template #formatter="{ value }">
              <span class="text-yellow-600 font-bold font-mono">{{ value }}</span>
            </template>
          </a-statistic>
        </div>

        <h4 class="text-md font-semibold text-gray-700 mb-3 border-b pb-2">其他详细信息</h4>
        <div class="grid grid-cols-2 gap-4">
          <div class="bg-gray-50 p-3 rounded border">
            <div class="text-gray-500 text-xs mb-1">模板贡献次数</div>
            <div class="font-bold text-lg text-blue-600">{{ currentUser?.total_contributions || 0 }}</div>
          </div>
          <div class="bg-gray-50 p-3 rounded border">
            <div class="text-gray-500 text-xs mb-1">模板采纳次数</div>
            <div class="font-bold text-lg text-gold-600">{{ currentUser?.approved_contributions || 0 }}</div>
          </div>
        </div>
      </div>
      <div v-else class="text-center text-gray-500 py-8">
        数据加载失败
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
