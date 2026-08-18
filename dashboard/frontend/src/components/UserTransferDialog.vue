<script setup lang="ts">
interface TransferUser { id: number; full_name?: string | null; username?: string | null }
interface SelectOption { label: string; value: number }

withDefaults(defineProps<{
  visible?: boolean
  loading?: boolean
  searchLoading?: boolean
  sourceUser?: TransferUser | null
  targetUserId?: number | null
  targetOptions?: SelectOption[]
  confirmText?: string
  note?: string
}>(), {
  visible: false,
  loading: false,
  searchLoading: false,
  sourceUser: null,
  targetUserId: null,
  targetOptions: () => [],
  confirmText: '',
  note: '后台用户数据转移',
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'update:targetUserId': [value: number]
  'update:confirmText': [value: string]
  'update:note': [value: string]
  'search-targets': [query: string]
  submit: []
}>()
</script>

<template>
  <a-modal
    :visible="visible"
    title="转移用户数据"
    width="720px"
    ok-text="确认转移"
    cancel-text="取消"
    ok-type="danger"
    :confirm-loading="loading"
    @update:visible="emit('update:visible', $event)"
    @ok="emit('submit')"
  >
    <div class="py-4">
      <div class="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
        此操作会把源用户的业务数据并入目标用户。源用户不会被删除，其 Telegram / Web 登录身份和封禁状态会保留，但灵石、充值、会员身份、签到、邀请、历史、返佣及社区数据会转移并从源账户清空；目标用户现有登录绑定不会改变。
      </div>

      <a-form layout="vertical">
        <a-form-item label="源用户">
          <a-input
            :value="sourceUser ? `${sourceUser.full_name || '未知用户'} (@${sourceUser.username || 'n/a'}) [ID:${sourceUser.id}]` : ''"
            disabled
          />
        </a-form-item>

        <a-form-item label="目标用户" required>
          <a-select
            :value="targetUserId"
            show-search
            :filter-option="false"
            :options="targetOptions"
            :not-found-content="searchLoading ? undefined : '无匹配用户'"
            placeholder="输入昵称 / 用户名 / ID 搜索目标用户"
            @search="emit('search-targets', $event)"
            @update:value="emit('update:targetUserId', $event)"
          >
            <template v-if="searchLoading" #notFoundContent>
              <a-spin size="small" />
            </template>
          </a-select>
        </a-form-item>

        <a-form-item label="管理员备注">
          <a-input
            :value="note"
            placeholder="例如：同一用户双账号合并"
            @update:value="emit('update:note', $event)"
          />
        </a-form-item>

        <a-form-item
          :label="`最终确认：请输入源用户 ID ${sourceUser?.id || ''}`"
          required
        >
          <a-input
            :value="confirmText"
            :placeholder="sourceUser ? `请输入 ${sourceUser.id}` : ''"
            @update:value="emit('update:confirmText', $event)"
          />
        </a-form-item>
      </a-form>
    </div>
  </a-modal>
</template>
