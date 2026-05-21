<script setup>
import { UserOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  formatDate: {
    type: Function,
    required: true,
  },
  allIdentities: {
    type: Array,
    required: true,
  },
  editIdentityVisible: {
    type: Boolean,
    default: false,
  },
  updatingIdentity: {
    type: Boolean,
    default: false,
  },
  currentIdentityUser: {
    type: Object,
    default: null,
  },
  newIdentityValue: {
    type: String,
    default: '外门弟子',
  },
  newExpireAtValue: {
    type: String,
    default: null,
  },
  autoConvertIdentity: {
    type: Boolean,
    default: true,
  },
  editGroupVisible: {
    type: Boolean,
    default: false,
  },
  updatingGroup: {
    type: Boolean,
    default: false,
  },
  currentGroupUser: {
    type: Object,
    default: null,
  },
  newGroupValue: {
    type: String,
    default: '凡人',
  },
  editChannelMemberVisible: {
    type: Boolean,
    default: false,
  },
  updatingChannelMember: {
    type: Boolean,
    default: false,
  },
  currentChannelMemberUser: {
    type: Object,
    default: null,
  },
  newChannelMemberValue: {
    type: Boolean,
    default: false,
  },
  editCreditsVisible: {
    type: Boolean,
    default: false,
  },
  updatingCredits: {
    type: Boolean,
    default: false,
  },
  currentEditingUser: {
    type: Object,
    default: null,
  },
  newCreditsValue: {
    type: Number,
    default: 0,
  },
  newCheckinCountValue: {
    type: Number,
    default: 0,
  },
  giftModalVisible: {
    type: Boolean,
    default: false,
  },
  giftingPlan: {
    type: Boolean,
    default: false,
  },
  currentGiftUser: {
    type: Object,
    default: null,
  },
  availablePlans: {
    type: Array,
    required: true,
  },
  giftForm: {
    type: Object,
    required: true,
  },
  statsModalVisible: {
    type: Boolean,
    default: false,
  },
  statsLoading: {
    type: Boolean,
    default: false,
  },
  currentUserStats: {
    type: Object,
    default: null,
  },
  currentUser: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits([
  'update:editIdentityVisible',
  'update:newIdentityValue',
  'update:newExpireAtValue',
  'update:autoConvertIdentity',
  'save-identity',
  'update:editGroupVisible',
  'update:newGroupValue',
  'save-group',
  'update:editChannelMemberVisible',
  'update:newChannelMemberValue',
  'save-channel-member',
  'update:editCreditsVisible',
  'update:newCreditsValue',
  'update:newCheckinCountValue',
  'save-credits',
  'update:giftModalVisible',
  'update:giftForm',
  'submit-gift',
  'update:statsModalVisible',
])

const updateGiftForm = (patch) => {
  emit('update:giftForm', {
    ...props.giftForm,
    ...patch,
  })
}
</script>

<template>
  <a-modal
    :visible="editIdentityVisible"
    title="切换用户身份组"
    :confirm-loading="updatingIdentity"
    ok-text="确认切换"
    cancel-text="取消"
    @update:visible="emit('update:editIdentityVisible', $event)"
    @ok="emit('save-identity')"
  >
    <div class="py-4">
      <p class="mb-4 text-gray-500">
        正在修改用户
        <span class="font-bold text-gray-800">{{ currentIdentityUser?.full_name || currentIdentityUser?.id }}</span>
        的身份等级
      </p>
      <a-form layout="vertical">
        <a-form-item label="身份组等级" required>
          <a-select
            :value="newIdentityValue"
            placeholder="请选择身份组"
            @update:value="emit('update:newIdentityValue', $event)"
          >
            <a-select-option v-for="idnt in allIdentities" :key="idnt" :value="idnt">
              {{ idnt }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="到期时间">
          <a-date-picker
            :value="newExpireAtValue"
            show-time
            value-format="YYYY-MM-DD HH:mm:ss"
            placeholder="选择到期时间（留空则不修改）"
            class="w-full"
            @update:value="emit('update:newExpireAtValue', $event)"
          />
        </a-form-item>
        <a-form-item v-if="!newExpireAtValue">
          <a-checkbox
            :checked="autoConvertIdentity"
            @update:checked="emit('update:autoConvertIdentity', $event)"
          >
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

  <a-modal
    :visible="editGroupVisible"
    title="切换用户修为"
    :confirm-loading="updatingGroup"
    ok-text="确认切换"
    cancel-text="取消"
    @update:visible="emit('update:editGroupVisible', $event)"
    @ok="emit('save-group')"
  >
    <div class="py-4">
      <p class="mb-4 text-gray-500">
        正在修改用户
        <span class="font-bold text-gray-800">{{ currentGroupUser?.full_name || currentGroupUser?.id }}</span>
        的修为
      </p>
      <a-form layout="vertical">
        <a-form-item label="修为类型">
          <a-select :value="newGroupValue" style="width: 100%" @update:value="emit('update:newGroupValue', $event)">
            <a-select-option value="凡人">凡人</a-select-option>
            <a-select-option value="练气期">练气期</a-select-option>
            <a-select-option value="筑基期">筑基期</a-select-option>
            <a-select-option value="金丹期">金丹期</a-select-option>
            <a-select-option value="元婴期">元婴期</a-select-option>
          </a-select>
        </a-form-item>
        <div class="text-xs text-gray-500 mt-1">
          注意：修为是基于用户在系统内的贡献和资历来决定的（如邀请人数、签到次数、生成图片数量等）。<br />
          手动更改修为可能会在系统下次重新评估时被覆盖。
        </div>
      </a-form>
    </div>
  </a-modal>

  <a-modal
    :visible="editChannelMemberVisible"
    title="切换入宗状态"
    :confirm-loading="updatingChannelMember"
    ok-text="确认切换"
    cancel-text="取消"
    @update:visible="emit('update:editChannelMemberVisible', $event)"
    @ok="emit('save-channel-member')"
  >
    <div class="py-4">
      <p class="mb-4 text-gray-500">
        正在修改用户
        <span class="font-bold text-gray-800">{{ currentChannelMemberUser?.full_name || currentChannelMemberUser?.id }}</span>
        的入宗状态
      </p>
      <a-form layout="vertical">
        <a-form-item label="是否已入宗门 (频道)">
          <a-switch
            :checked="newChannelMemberValue"
            checked-children="是"
            un-checked-children="否"
            @update:checked="emit('update:newChannelMemberValue', $event)"
          />
        </a-form-item>
        <div class="text-xs text-gray-500 mt-1">
          注意：如果用户实际并未加入官方频道，即使用此开关强制修改，当用户下次与机器人交互时，系统重新校验 Telegram 接口后，状态仍可能被重置。
        </div>
      </a-form>
    </div>
  </a-modal>

  <a-modal
    :visible="editCreditsVisible"
    title="修改用户数据"
    :confirm-loading="updatingCredits"
    ok-text="保存"
    cancel-text="取消"
    @update:visible="emit('update:editCreditsVisible', $event)"
    @ok="emit('save-credits')"
  >
    <div class="py-4">
      <p class="mb-4 text-gray-500">
        正在为用户
        <span class="font-bold text-gray-800">{{ currentEditingUser?.full_name || currentEditingUser?.id }}</span>
        修改数据
      </p>
      <a-form layout="vertical">
        <a-form-item label="永久灵石余额">
          <a-input-number :value="newCreditsValue" :min="0" class="w-full" @update:value="emit('update:newCreditsValue', $event)" />
        </a-form-item>
        <a-form-item label="累计签到次数">
          <a-input-number :value="newCheckinCountValue" :min="0" class="w-full" @update:value="emit('update:newCheckinCountValue', $event)" />
        </a-form-item>
      </a-form>
      <p class="mt-2 text-xs text-amber-500 italic">* 增加数值直接输入更大数值，减少数值输入较小数值即可。</p>
    </div>
  </a-modal>

  <a-modal
    :visible="giftModalVisible"
    title="赠送/补发套餐"
    :confirm-loading="giftingPlan"
    ok-text="确认赠送"
    cancel-text="取消"
    @update:visible="emit('update:giftModalVisible', $event)"
    @ok="emit('submit-gift')"
  >
    <div class="py-4">
      <p class="mb-4 text-gray-500">
        正在为用户
        <span class="font-bold text-gray-800">{{ currentGiftUser?.full_name || currentGiftUser?.id }}</span>
        发放权益
      </p>
      <a-form layout="vertical">
        <a-form-item label="选择套餐" required>
          <a-select
            :value="giftForm.plan_id"
            placeholder="请选择要赠送的套餐"
            @update:value="updateGiftForm({ plan_id: $event })"
          >
            <a-select-option v-for="plan in availablePlans" :key="plan.id" :value="plan.id">
              {{ plan.name }} (送 {{ plan.reward_credits }} 灵石 / 境界: {{ plan.identity_name }})
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="操作备注" required>
          <a-input
            :value="giftForm.note"
            placeholder="例如: 客诉补偿 / 内部赠送"
            @update:value="updateGiftForm({ note: $event })"
          />
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

  <a-modal
    :visible="statsModalVisible"
    title="用户详细统计"
    :footer="null"
    width="600px"
    @update:visible="emit('update:statsModalVisible', $event)"
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
</template>
