<script setup>
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { fetchPlans, createPlan, updatePlan, deletePlan, fetchOrders } from '../api/api'

// Plans state
const plans = ref([])
const plansLoading = ref(false)
const planModalVisible = ref(false)
const planForm = ref({
  id: null,
  name: '',
  identity_name: '',
  price_ton: 0.1,
  price_stars: 100,
  price_rmb: 30.00,
  reward_credits: 100,
  duration_days: 30,
  is_active: true
})

// Orders state
const orders = ref([])
const ordersTotal = ref(0)
const ordersLoading = ref(false)
const currentOrderPage = ref(1)
const orderPageSize = ref(10)
const orderStatusFilter = ref('ALL')

const planColumns = [
  { title: '套餐名称', dataIndex: 'name', key: 'name' },
  { title: '身份境界', dataIndex: 'identity_name', key: 'identity_name' },
  { title: '价格 (TON)', dataIndex: 'price_ton', key: 'price_ton' },
  { title: '价格 (Stars)', dataIndex: 'price_stars', key: 'price_stars' },
  { title: '价格 (RMB)', dataIndex: 'price_rmb', key: 'price_rmb' },
  { title: '奖励灵石', dataIndex: 'reward_credits', key: 'reward_credits' },
  { title: '有效期 (天)', dataIndex: 'duration_days', key: 'duration_days' },
  { title: '状态', dataIndex: 'is_active', key: 'is_active' },
  { title: '操作', key: 'action' }
]

const orderColumns = [
  { title: '订单号', dataIndex: 'order_id', key: 'order_id', ellipsis: true },
  { title: '用户ID', dataIndex: 'telegram_id', key: 'telegram_id' },
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '套餐', dataIndex: 'plan_name', key: 'plan_name' },
  { title: '支付金额', dataIndex: 'final_price', key: 'final_price' },
  { title: '状态', dataIndex: 'status', key: 'status' },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
]

const loadPlans = async () => {
  plansLoading.value = true
  try {
    plans.value = await fetchPlans()
  } catch (err) {
    message.error('加载套餐失败')
  } finally {
    plansLoading.value = false
  }
}

const loadOrders = async (page = 1) => {
  ordersLoading.value = true
  currentOrderPage.value = page
  try {
    const res = await fetchOrders(page, orderPageSize.value, orderStatusFilter.value)
    orders.value = res.items
    ordersTotal.value = res.total
  } catch (err) {
    message.error('加载订单失败')
  } finally {
    ordersLoading.value = false
  }
}

const handleOrderTableChange = (pagination) => {
  loadOrders(pagination.current)
}

const openPlanModal = (record = null) => {
  if (record) {
    planForm.value = { ...record }
  } else {
    planForm.value = {
      id: null,
      name: '',
      identity_name: '',
      price_ton: 0.1,
      price_stars: 100,
      price_rmb: 30.00,
      reward_credits: 100,
      duration_days: 30,
      is_active: true
    }
  }
  planModalVisible.value = true
}

const savePlan = async () => {
  try {
    if (planForm.value.id) {
      await updatePlan(planForm.value.id, planForm.value)
      message.success('更新成功')
    } else {
      await createPlan(planForm.value)
      message.success('创建成功')
    }
    planModalVisible.value = false
    loadPlans()
  } catch (err) {
    message.error('保存失败')
  }
}

const confirmDeletePlan = async (id) => {
  try {
    await deletePlan(id)
    message.success('删除成功')
    loadPlans()
  } catch (err) {
    message.error('删除失败')
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  loadPlans()
  loadOrders()
})
</script>

<template>
  <div class="h-full flex flex-col gap-4">
    <a-tabs default-active-key="plans" class="bg-white rounded-xl shadow-sm border p-4 flex-1 overflow-hidden flex flex-col">
      <a-tab-pane key="plans" tab="商品套餐配置">
        <div class="flex justify-between mb-4">
          <h2 class="text-lg font-bold">套餐列表</h2>
          <a-button type="primary" @click="openPlanModal(null)">添加新套餐</a-button>
        </div>
        <a-table 
          :columns="planColumns" 
          :data-source="plans" 
          :loading="plansLoading"
          :row-key="(record) => record.id"
          :pagination="false"
          size="middle"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'is_active'">
              <a-tag :color="record.is_active ? 'green' : 'red'">
                {{ record.is_active ? '启用' : '禁用' }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'action'">
              <a-button type="link" @click="openPlanModal(record)">编辑</a-button>
              <a-popconfirm
                title="确定要删除这个套餐吗？"
                @confirm="confirmDeletePlan(record.id)"
              >
                <a-button type="link" danger>删除</a-button>
              </a-popconfirm>
            </template>
          </template>
        </a-table>
      </a-tab-pane>
      
      <a-tab-pane key="orders" tab="充值订单记录">
        <div class="flex justify-between mb-4 items-center">
          <h2 class="text-lg font-bold">订单列表</h2>
          <div class="flex gap-2">
            <a-select v-model:value="orderStatusFilter" style="width: 120px" @change="loadOrders(1)">
              <a-select-option value="ALL">全部状态</a-select-option>
              <a-select-option value="PENDING">处理中</a-select-option>
              <a-select-option value="SUCCESS">成功</a-select-option>
              <a-select-option value="FAILED">失败</a-select-option>
            </a-select>
            <a-button @click="loadOrders(1)">刷新</a-button>
          </div>
        </div>
        <a-table 
          :columns="orderColumns" 
          :data-source="orders" 
          :loading="ordersLoading"
          :row-key="(record) => record.id"
          :pagination="{ current: currentOrderPage, pageSize: orderPageSize, total: ordersTotal }"
          @change="handleOrderTableChange"
          size="middle"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <a-tag :color="record.status === 'SUCCESS' ? 'green' : record.status === 'FAILED' ? 'red' : 'orange'">
                {{ record.status || '未知' }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'final_price'">
              <span v-if="record.tx_hash && String(record.tx_hash).startsWith('manual_')">赠送 (0)</span>
              <span v-else-if="record.order_id && String(record.order_id).startsWith('RMB_')">¥ {{ record.final_price }}</span>
              <span v-else-if="record.final_price >= 50">{{ record.final_price }} Stars</span>
              <span v-else-if="record.final_price !== undefined">{{ record.final_price }} TON</span>
              <span v-else>-</span>
            </template>
            <template v-else-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
          </template>
        </a-table>
      </a-tab-pane>
    </a-tabs>

    <!-- Plan Edit Modal -->
    <a-modal
      v-model:visible="planModalVisible"
      :title="planForm.id ? '编辑套餐' : '添加新套餐'"
      @ok="savePlan"
      okText="保存"
      cancelText="取消"
    >
      <a-form :model="planForm" layout="vertical">
        <a-form-item label="套餐名称" required>
          <a-input v-model:value="planForm.name" placeholder="例如: 基础月卡" />
        </a-form-item>
        <a-form-item label="晋升境界" required>
          <a-input v-model:value="planForm.identity_name" placeholder="例如: 内门弟子" />
        </a-form-item>
        <a-form-item label="价格 (TON)" required>
          <a-input-number v-model:value="planForm.price_ton" :min="0" :step="0.1" style="width: 100%" />
        </a-form-item>
        <a-form-item label="价格 (Stars)" required>
          <a-input-number v-model:value="planForm.price_stars" :min="0" :step="10" style="width: 100%" />
        </a-form-item>
        <a-form-item label="价格 (RMB/¥)" required>
          <a-input-number v-model:value="planForm.price_rmb" :min="0" :step="1.0" style="width: 100%" />
        </a-form-item>
        <a-form-item label="包含灵石数量" required>
          <a-input-number v-model:value="planForm.reward_credits" :min="0" :step="10" style="width: 100%" />
        </a-form-item>
        <a-form-item label="有效天数" required>
          <a-input-number v-model:value="planForm.duration_days" :min="1" :step="1" style="width: 100%" />
        </a-form-item>
        <a-form-item label="是否启用">
          <a-switch v-model:checked="planForm.is_active" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
