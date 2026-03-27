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
  StarOutlined
} from '@ant-design/icons-vue'

defineProps({
  stats: {
    type: Object,
    required: true
  }
})
</script>

<template>
  <a-row :gutter="[16, 16]" class="mb-6">
    <a-col :xs="24" :sm="12" :md="8" :lg="4">
      <a-card hoverable class="stat-card">
        <a-statistic
          title="TON 钱包余额"
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
          title="Stars 余额"
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
        <div class="mt-2 text-xs">
          <a-tooltip title="每日 00:00 自动清零">
            <a-tag color="orange" class="m-0 border-0 flex items-center justify-between cursor-help transition-all duration-300" :class="{ 'animate-pulse bg-orange-100': stats.total_temporary_ingot >= 1000 }">
              <span>临时灵石</span>
              <span class="font-bold ml-1">{{ stats.total_temporary_ingot || 0 }}</span>
            </a-tag>
          </a-tooltip>
        </div>
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
        <div class="mt-2 text-xs">
          <a-tooltip title="每日 00:00 自动清零">
            <a-tag color="orange" class="m-0 border-0 flex items-center justify-between cursor-help transition-all duration-300" :class="{ 'animate-pulse bg-orange-100': stats.total_active_temporary_ingot >= 1000 }">
              <span>临时灵石</span>
              <span class="font-bold ml-1">{{ stats.total_active_temporary_ingot || 0 }}</span>
            </a-tag>
          </a-tooltip>
        </div>
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
