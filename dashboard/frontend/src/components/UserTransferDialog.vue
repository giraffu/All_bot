<script setup>
const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  searchLoading: {
    type: Boolean,
    default: false,
  },
  sourceUser: {
    type: Object,
    default: null,
  },
  targetUserId: {
    type: Number,
    default: null,
  },
  targetOptions: {
    type: Array,
    default: () => [],
  },
  confirmText: {
    type: String,
    default: '',
  },
  note: {
    type: String,
    default: '后台用户数据转移',
  },
})

const emit = defineEmits([
  'update:visible',
  'update:targetUserId',
  'update:confirmText',
  'update:note',
  'search-targets',
  'submit',
])
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
        此操作会把源用户的全量业务数据并入目标用户，并删除源用户。当前实现会转移灵石、订单、返佣、历史、收藏/投稿/评论/互动、签到与邀请关系，不会改动目标用户现有的 Telegram / Web 登录绑定。
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
