<script setup>
import { 
  UserOutlined, 
  CloudUploadOutlined, 
  DollarCircleOutlined,
  UserAddOutlined,
  RiseOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  FireOutlined,
  CrownOutlined,
  WalletOutlined,
  StarOutlined,
  GlobalOutlined
} from '@ant-design/icons-vue'

defineProps({
  stats: {
    type: Object,
    required: true
  },
  mode: {
    type: String,
    default: 'user' // 'user' or 'finance'
  }
})
</script>

<template>
  <a-row :gutter="[16, 16]" class="mb-6" v-if="mode === 'finance'">
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="TON 真实余额"
          :value="stats.ton_balance || 0"
          :precision="2"
          :value-style="{ color: '#1890ff' }"
        >
          <template #prefix>
            <wallet-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="USDT 真实余额"
          :value="stats.usdt_balance || 0"
          :precision="2"
          :value-style="{ color: '#52c41a' }"
        >
          <template #prefix>
            <wallet-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="用户支付的 Stars"
          :value="stats.star_balance || 0"
          :value-style="{ color: '#faad14' }"
        >
          <template #prefix>
            <star-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="RMB 累计充值收入"
          :value="stats.rmb_balance || 0"
          :precision="2"
          :value-style="{ color: '#f5222d' }"
        >
          <template #prefix>
            <span class="mr-1">¥</span>
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="内门弟子数"
          :value="stats.inner_disciple_count || 0"
          :value-style="{ color: '#1890ff' }"
        >
          <template #prefix>
            <crown-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="核心弟子数"
          :value="stats.core_disciple_count || 0"
          :value-style="{ color: '#722ed1' }"
        >
          <template #prefix>
            <crown-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="真传弟子数"
          :value="stats.true_disciple_count || 0"
          :value-style="{ color: '#eb2f96' }"
        >
          <template #prefix>
            <crown-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="受邀充值(TON)"
          :value="stats.total_invitation_ton || 0"
          :precision="2"
          :value-style="{ color: '#1890ff' }"
        >
          <template #prefix>
            <wallet-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="受邀充值(Stars)"
          :value="stats.total_invitation_stars || 0"
          :value-style="{ color: '#faad14' }"
        >
          <template #prefix>
            <star-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="受邀充值(RMB)"
          :value="stats.total_invitation_rmb || 0"
          :precision="2"
          :value-style="{ color: '#f5222d' }"
        >
          <template #prefix>
            <span class="mr-1">¥</span>
          </template>
        </a-statistic>
      </a-card>
    </a-col>
  </a-row>

  <a-row :gutter="[16, 16]" class="mb-6" v-if="mode === 'user'">
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="今日新增用户"
          :value="stats.today_users"
          :value-style="{ color: '#1890ff' }"
        >
          <template #prefix>
            <rise-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="今日新用户（虚）"
          :value="stats.today_users_all"
          :value-style="{ color: '#722ed1' }"
        >
          <template #prefix>
            <user-add-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="今日活跃用户"
          :value="stats.today_active_users"
          :value-style="{ color: '#faad14' }"
        >
          <template #prefix>
            <user-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="今日Web活跃用户"
          :value="stats.today_web_users || 0"
          :value-style="{ color: '#faad14' }"
        >
          <template #prefix>
            <global-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="今日生成量"
          :value="stats.today_generations"
          :value-style="{ color: '#52c41a' }"
        >
          <template #prefix>
            <thunderbolt-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="今日签到人数"
          :value="stats.today_checkins"
          :value-style="{ color: '#13c2c2' }"
        >
          <template #prefix>
            <check-circle-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="今日消耗灵石"
          :value="stats.today_consumed_credits"
          :value-style="{ color: '#eb2f96' }"
        >
          <template #prefix>
            <fire-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="总用户数"
          :value="stats.total_users"
          :value-style="{ color: '#666' }"
        >
          <template #prefix>
            <user-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="总英文用户"
          :value="stats.total_en_users || 0"
          :value-style="{ color: '#1890ff' }"
        >
          <template #prefix>
            <user-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="总中文用户"
          :value="stats.total_zh_users || 0"
          :value-style="{ color: '#faad14' }"
        >
          <template #prefix>
            <user-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="总Web创作者"
          :value="stats.total_web_users || 0"
          :value-style="{ color: '#666' }"
        >
          <template #prefix>
            <global-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="总生成量"
          :value="stats.total_generations"
          :value-style="{ color: '#666' }"
        >
          <template #prefix>
            <cloud-upload-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="总邀请数"
          :value="stats.total_referrals"
          :value-style="{ color: '#faad14' }"
        >
          <template #prefix>
            <user-add-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card relative overflow-hidden">
        <a-statistic
          title="流通灵石"
          :value="stats.total_credits"
          :value-style="{ color: '#722ed1' }"
        >
          <template #prefix>
            <dollar-circle-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card relative overflow-hidden">
        <a-statistic
          title="流通灵石（活跃）"
          :value="stats.total_active_credits"
          :value-style="{ color: '#b37feb' }"
        >
          <template #prefix>
            <dollar-circle-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="累计模板贡献"
          :value="stats.total_template_contributions"
          :value-style="{ color: '#1890ff' }"
        >
          <template #prefix>
            <cloud-upload-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="已采纳模板"
          :value="stats.total_approved_contributions"
          :value-style="{ color: '#52c41a' }"
        >
          <template #prefix>
            <check-circle-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="密码注册用户"
          :value="stats.total_password_users || 0"
          :value-style="{ color: '#13c2c2' }"
        >
          <template #prefix>
            <safety-certificate-outlined />
          </template>
        </a-statistic>
      </a-card>
    </a-col>
  </a-row>
</template>

<style scoped>
.stat-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: .8;
    transform: scale(1.05);
  }
}
.animate-pulse {
  animation: pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
</style>
