<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import message from 'ant-design-vue/es/message'

import {
  createSiteNotice,
  deleteSiteNotice,
  fetchSiteNotices,
  updateSiteNotice,
} from '../api/api'

interface SiteNoticePayload {
  id?: number | null
  title: string
  content: string
  is_active: boolean
  is_pinned: boolean
  target_groups: string[]
  target_identities: string[]
  published_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

interface SelectOption {
  label: string
  value: string
}

const groupOptions: SelectOption[] = [
  { label: '凡人', value: '凡人' },
  { label: '练气期', value: '练气期' },
  { label: '筑基期', value: '筑基期' },
  { label: '金丹期', value: '金丹期' },
  { label: '元婴期', value: '元婴期' },
  { label: '化神期', value: '化神期' },
  { label: '炼虚期', value: '炼虚期' },
  { label: '合体期', value: '合体期' },
  { label: '大乘期', value: '大乘期' },
  { label: '渡劫期', value: '渡劫期' },
]

const identityOptions: SelectOption[] = [
  { label: '外门弟子', value: '外门弟子' },
  { label: '内门弟子', value: '内门弟子' },
  { label: '核心弟子', value: '核心弟子' },
  { label: '真传弟子', value: '真传弟子' },
]

const createEmptyForm = (): SiteNoticePayload => ({
  id: null,
  title: '',
  content: '',
  is_active: false,
  is_pinned: false,
  target_groups: [],
  target_identities: [],
  published_at: null,
  created_at: null,
  updated_at: null,
})

const cloneNotice = (notice: Partial<SiteNoticePayload>): SiteNoticePayload => ({
  id: notice.id ?? null,
  title: notice.title ?? '',
  content: notice.content ?? '',
  is_active: Boolean(notice.is_active),
  is_pinned: Boolean(notice.is_pinned),
  target_groups: [...(notice.target_groups ?? [])],
  target_identities: [...(notice.target_identities ?? [])],
  published_at: notice.published_at ?? null,
  created_at: notice.created_at ?? null,
  updated_at: notice.updated_at ?? null,
})

const loading = ref(false)
const saving = ref(false)
const togglingPinId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const notices = ref<SiteNoticePayload[]>([])
const selectedNoticeId = ref<number | null>(null)
const form = ref<SiteNoticePayload>(createEmptyForm())

const isCreateMode = computed(() => !form.value.id)
const contentLength = computed(() => form.value.content.length)
const effectiveVisible = computed(() => form.value.is_active && form.value.content.trim().length > 0)
const selectedNotice = computed(() =>
  notices.value.find((notice) => notice.id === selectedNoticeId.value) ?? null
)
const audienceSummary = computed(() => describeAudience(form.value))

function describeAudience(notice: Pick<SiteNoticePayload, 'target_groups' | 'target_identities'>) {
  const parts: string[] = []
  if (notice.target_groups.length > 0) {
    parts.push(`修为：${notice.target_groups.join('、')}`)
  }
  if (notice.target_identities.length > 0) {
    parts.push(`身份：${notice.target_identities.join('、')}`)
  }
  return parts.length > 0 ? parts.join('；') : '所有 Web 用户'
}

const formatTime = (value?: string | null) => {
  if (!value) {
    return '未发布'
  }
  return new Date(value).toLocaleString('zh-CN')
}

const applySelection = (notice: SiteNoticePayload | null) => {
  selectedNoticeId.value = notice?.id ?? null
  form.value = notice ? cloneNotice(notice) : createEmptyForm()
}

const loadSiteNotices = async () => {
  loading.value = true
  try {
    const payload = await fetchSiteNotices()
    notices.value = (payload.items ?? []).map((item: SiteNoticePayload) => cloneNotice(item))

    if (selectedNoticeId.value) {
      const matched = notices.value.find((notice) => notice.id === selectedNoticeId.value) ?? null
      applySelection(matched)
      if (matched) {
        return
      }
    }

    applySelection(notices.value[0] ?? null)
  } catch {
    message.error('加载通知列表失败')
  } finally {
    loading.value = false
  }
}

const selectNotice = (notice: SiteNoticePayload) => {
  applySelection(notice)
}

const startCreateNotice = () => {
  applySelection(null)
}

const saveSiteNotice = async () => {
  saving.value = true
  try {
    const payload = {
      title: form.value.title,
      content: form.value.content,
      is_active: form.value.is_active,
      is_pinned: form.value.is_pinned,
      target_groups: form.value.target_groups,
      target_identities: form.value.target_identities,
    }

    const saved = form.value.id
      ? await updateSiteNotice(form.value.id, payload)
      : await createSiteNotice(payload)

    selectedNoticeId.value = saved.id ?? null
    await loadSiteNotices()
    message.success(saved.is_active ? '通知已保存并发布' : '通知草稿已保存')
  } catch {
    message.error('保存通知失败')
  } finally {
    saving.value = false
  }
}

const handleTogglePinned = async (notice: SiteNoticePayload) => {
  if (!notice.id) {
    return
  }
  togglingPinId.value = notice.id
  try {
    const updated = await updateSiteNotice(notice.id, {
      title: notice.title,
      content: notice.content,
      is_active: notice.is_active,
      is_pinned: !notice.is_pinned,
      target_groups: notice.target_groups,
      target_identities: notice.target_identities,
    })
    selectedNoticeId.value = updated.id ?? selectedNoticeId.value
    await loadSiteNotices()
    message.success(updated.is_pinned ? '通知已置顶' : '通知已取消置顶')
  } catch {
    message.error('更新置顶状态失败')
  } finally {
    togglingPinId.value = null
  }
}

const handleDeleteNotice = async (notice: SiteNoticePayload) => {
  if (!notice.id) {
    return
  }
  deletingId.value = notice.id
  try {
    await deleteSiteNotice(notice.id)
    if (selectedNoticeId.value === notice.id) {
      selectedNoticeId.value = null
    }
    await loadSiteNotices()
    message.success('通知已删除')
  } catch {
    message.error('删除通知失败')
  } finally {
    deletingId.value = null
  }
}

onMounted(() => {
  void loadSiteNotices()
})
</script>

<template>
  <div class="flex-1 flex flex-col gap-6">
    <a-card :loading="loading" title="Web 通知中心" class="shadow-sm">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
        <div>
          <div class="text-base font-semibold text-slate-900">多条通知、历史查看、置顶与软删除</div>
          <div class="mt-1 text-sm text-slate-500">
            顶部默认展示用户可见范围内的置顶通知；用户可点开通知中心查看历史。
          </div>
        </div>
        <a-button type="primary" @click="startCreateNotice">新增通知</a-button>
      </div>

      <div class="site-notice-admin-layout">
        <aside class="site-notice-admin-list">
          <div class="mb-3 flex items-center justify-between">
            <div class="text-sm font-semibold text-slate-800">通知历史</div>
            <div class="text-xs text-slate-400">{{ notices.length }} 条</div>
          </div>

          <div v-if="notices.length === 0" class="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-400">
            还没有通知，点击右上角“新增通知”开始创建。
          </div>

          <button
            v-for="notice in notices"
            :key="notice.id"
            type="button"
            class="site-notice-admin-item"
            :class="{ 'site-notice-admin-item--active': selectedNotice?.id === notice.id }"
            @click="selectNotice(notice)"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-sm font-semibold text-slate-900">
                  {{ notice.title || '未命名通知' }}
                </div>
                <div class="mt-1 text-xs text-slate-400">
                  {{ formatTime(notice.published_at || notice.updated_at || notice.created_at) }}
                </div>
              </div>
              <div class="flex shrink-0 items-center gap-1">
                <a-tag v-if="notice.is_pinned" color="gold">置顶</a-tag>
                <a-tag :color="notice.is_active ? 'green' : 'default'">
                  {{ notice.is_active ? '启用中' : '草稿' }}
                </a-tag>
              </div>
            </div>

            <div class="mt-2 line-clamp-2 text-left text-xs leading-5 text-slate-500">
              {{ notice.content || '暂无正文' }}
            </div>

            <div class="mt-3 flex items-center justify-between gap-2">
              <span class="text-[11px] text-slate-400">{{ describeAudience(notice) }}</span>
              <div class="flex items-center gap-2">
                <a-button
                  size="small"
                  :loading="togglingPinId === notice.id"
                  @click.stop="handleTogglePinned(notice)"
                >
                  {{ notice.is_pinned ? '取消置顶' : '置顶' }}
                </a-button>
                <a-popconfirm
                  title="确认删除这条通知吗？"
                  ok-text="删除"
                  cancel-text="取消"
                  @confirm="handleDeleteNotice(notice)"
                >
                  <a-button
                    danger
                    size="small"
                    :loading="deletingId === notice.id"
                    @click.stop
                  >
                    删除
                  </a-button>
                </a-popconfirm>
              </div>
            </div>
          </button>
        </aside>

        <section class="site-notice-admin-editor">
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div>
              <div class="text-base font-semibold text-slate-900">
                {{ isCreateMode ? '新建通知' : `编辑通知 #${form.id}` }}
              </div>
              <div class="mt-1 text-sm text-slate-500">
                发布时间：{{ formatTime(form.published_at) }} ｜ 最近更新：{{ formatTime(form.updated_at) }}
              </div>
            </div>
            <div class="flex items-center gap-3">
              <span class="text-sm text-slate-500">启用</span>
              <a-switch v-model:checked="form.is_active" />
              <span class="text-sm text-slate-500">置顶</span>
              <a-switch v-model:checked="form.is_pinned" :disabled="!form.is_active || !form.content.trim()" />
            </div>
          </div>

          <a-form layout="vertical">
            <a-form-item label="通知标题">
              <a-input
                v-model:value="form.title"
                :maxlength="255"
                placeholder="例如：系统维护公告 / 节日福利通知"
                show-count
              />
            </a-form-item>

            <a-form-item label="通知正文">
              <a-textarea
                v-model:value="form.content"
                :rows="8"
                :maxlength="5000"
                placeholder="例如：今晚 23:00 - 23:30 系统维护，期间部分功能可能短暂不可用。"
                show-count
              />
              <div class="mt-2 text-xs text-slate-400">
                当前字数：{{ contentLength }}。只有启用且正文非空时，通知才会进入 Web 历史并可能展示为顶部入口。
              </div>
            </a-form-item>

            <a-form-item label="可见修为">
              <a-select
                v-model:value="form.target_groups"
                mode="multiple"
                :options="groupOptions"
                placeholder="不限制修为（默认所有用户）"
                allow-clear
                show-search
                option-filter-prop="label"
                max-tag-count="responsive"
              />
            </a-form-item>

            <a-form-item label="可见身份">
              <a-select
                v-model:value="form.target_identities"
                mode="multiple"
                :options="identityOptions"
                placeholder="不限制身份（默认所有用户）"
                allow-clear
                show-search
                option-filter-prop="label"
                max-tag-count="responsive"
              />
              <div class="mt-2 text-xs text-slate-400">
                修为和身份任一命中即显示；两项都不选表示所有 Web 用户可见。
              </div>
            </a-form-item>
          </a-form>

          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="text-sm text-slate-500">可见范围：{{ audienceSummary }}</div>
            <a-button type="primary" :loading="saving" @click="saveSiteNotice">
              {{ isCreateMode ? '创建通知' : '保存修改' }}
            </a-button>
          </div>
        </section>
      </div>
    </a-card>

    <a-card title="前台预览" class="shadow-sm">
      <div
        class="rounded-xl border px-4 py-3"
        :class="
          effectiveVisible
            ? 'border-amber-200 bg-amber-50 text-amber-900'
            : 'border-slate-200 bg-slate-50 text-slate-500'
        "
      >
        <div class="flex flex-wrap items-center gap-2 text-sm font-semibold">
          <span>{{ form.title.trim() || '站点通知' }}</span>
          <a-tag v-if="form.is_pinned && effectiveVisible" color="gold">置顶</a-tag>
          <a-tag :color="effectiveVisible ? 'green' : 'default'">
            {{ effectiveVisible ? '会展示在 Web 顶部/历史中' : '当前不会向 Web 用户展示' }}
          </a-tag>
        </div>
        <div class="mt-1 text-xs opacity-80">
          可见范围：{{ audienceSummary }}
        </div>
        <div class="mt-2 whitespace-pre-wrap text-sm leading-6">
          {{ form.content.trim() || '这里会显示通知正文预览。' }}
        </div>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.site-notice-admin-layout {
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: 20px;
}

.site-notice-admin-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.site-notice-admin-item {
  width: 100%;
  text-align: left;
  border: 1px solid rgba(226, 232, 240, 1);
  border-radius: 16px;
  padding: 14px;
  background: #fff;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.site-notice-admin-item:hover,
.site-notice-admin-item--active {
  border-color: rgba(250, 173, 20, 0.55);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  transform: translateY(-1px);
}

.site-notice-admin-editor {
  min-width: 0;
}

@media (max-width: 1024px) {
  .site-notice-admin-layout {
    grid-template-columns: 1fr;
  }
}
</style>
