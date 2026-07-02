<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons-vue'

import { fetchQqccBotConfig, updateQqccBotConfig } from '../api/api'

type MainButtonKey = 'quick_undress' | 'photo_edit' | 'video_edit' | 'market' | 'main_bot_link'
type PhotoButtonKey = 'masturbation' | 'random_faceswap'
type UndressMethodKey = 'legacy' | 'i2i_draw'
type VideoButtonKey = 'missionary' | 'doggy' | 'blowjob' | 'undress_tongue' | 'closeup_blowjob'
type ResolutionKey = '512p' | '720p' | '1024p'
type DurationKey = '5s' | '8s' | '10s'
type PromptKey =
  | 'undress'
  | 'i2i_draw_quick_undress'
  | 'masturbation'
  | 'face_swap'
  | 'perfect_video_insert'
  | 'doggy_style'
  | 'blowjob'
  | 'undress_tongue'
  | 'closeup_blowjob'

interface QqccBotConfig {
  global_enabled: boolean
  main_buttons: Record<MainButtonKey, boolean>
  photo_buttons: Record<PhotoButtonKey, boolean>
  undress_methods: Record<UndressMethodKey, boolean>
  video_buttons: Record<VideoButtonKey, boolean>
  video_settings: {
    resolutions: Record<ResolutionKey, boolean>
    durations: Record<DurationKey, boolean>
  }
  prompts: Record<PromptKey, string>
}

interface QqccBotConfigResponse {
  key?: string
  updated_at?: string | null
  config?: Partial<QqccBotConfig>
}

const defaultConfig = (): QqccBotConfig => ({
  global_enabled: true,
  main_buttons: {
    quick_undress: true,
    photo_edit: true,
    video_edit: true,
    market: true,
    main_bot_link: true,
  },
  photo_buttons: {
    masturbation: true,
    random_faceswap: true,
  },
  undress_methods: {
    legacy: true,
    i2i_draw: true,
  },
  video_buttons: {
    missionary: true,
    doggy: true,
    blowjob: true,
    undress_tongue: true,
    closeup_blowjob: true,
  },
  video_settings: {
    resolutions: {
      '512p': true,
      '720p': true,
      '1024p': true,
    },
    durations: {
      '5s': true,
      '8s': true,
      '10s': true,
    },
  },
  prompts: {
    undress: '',
    i2i_draw_quick_undress: '',
    masturbation: '',
    face_swap: '',
    perfect_video_insert: '',
    doggy_style: '',
    blowjob: '',
    undress_tongue: '',
    closeup_blowjob: '',
  },
})

const mainButtonOptions: Array<{ key: MainButtonKey; label: string }> = [
  { key: 'quick_undress', label: '快速脱衣' },
  { key: 'photo_edit', label: '懒人P图' },
  { key: 'video_edit', label: 'AI动图' },
  { key: 'market', label: '修仙市集' },
  { key: 'main_bot_link', label: '前往主bot' },
]

const photoButtonOptions: Array<{ key: PhotoButtonKey; label: string }> = [
  { key: 'masturbation', label: '快速自慰' },
  { key: 'random_faceswap', label: '随机换脸' },
]

const undressMethodOptions: Array<{ key: UndressMethodKey; label: string }> = [
  { key: 'legacy', label: '头像/半身补全' },
  { key: 'i2i_draw', label: '全身保脸重绘' },
]

const videoButtonOptions: Array<{ key: VideoButtonKey; label: string }> = [
  { key: 'missionary', label: '动图传教士' },
  { key: 'doggy', label: '动图后入' },
  { key: 'blowjob', label: '口交' },
  { key: 'undress_tongue', label: '脱衣吐舌' },
  { key: 'closeup_blowjob', label: '特写口交' },
]

const resolutionOptions: ResolutionKey[] = ['512p', '720p', '1024p']
const durationOptions: DurationKey[] = ['5s', '8s', '10s']

const promptOptions: Array<{ key: PromptKey; label: string }> = [
  { key: 'undress', label: '快速脱衣' },
  { key: 'i2i_draw_quick_undress', label: '全身保脸重绘' },
  { key: 'masturbation', label: '快速自慰' },
  { key: 'face_swap', label: '随机换脸' },
  { key: 'perfect_video_insert', label: '动图传教士' },
  { key: 'doggy_style', label: '动图后入' },
  { key: 'blowjob', label: '口交' },
  { key: 'undress_tongue', label: '脱衣吐舌' },
  { key: 'closeup_blowjob', label: '特写口交' },
]

const loading = ref(false)
const saving = ref(false)
const configKey = ref('')
const updatedAt = ref<string | null>(null)
const config = reactive<QqccBotConfig>(defaultConfig())

const statusText = computed(() => (config.global_enabled ? '开启' : '关闭'))
const updatedAtText = computed(() => updatedAt.value || '-')

const mergeConfig = (raw?: Partial<QqccBotConfig>): QqccBotConfig => {
  const merged = defaultConfig()
  if (!raw || typeof raw !== 'object') return merged
  if (typeof raw.global_enabled === 'boolean') {
    merged.global_enabled = raw.global_enabled
  }

  mainButtonOptions.forEach(({ key }) => {
    const value = raw.main_buttons?.[key]
    if (typeof value === 'boolean') merged.main_buttons[key] = value
  })
  photoButtonOptions.forEach(({ key }) => {
    const value = raw.photo_buttons?.[key]
    if (typeof value === 'boolean') merged.photo_buttons[key] = value
  })
  undressMethodOptions.forEach(({ key }) => {
    const value = raw.undress_methods?.[key]
    if (typeof value === 'boolean') merged.undress_methods[key] = value
  })
  videoButtonOptions.forEach(({ key }) => {
    const value = raw.video_buttons?.[key]
    if (typeof value === 'boolean') merged.video_buttons[key] = value
  })
  resolutionOptions.forEach((key) => {
    const value = raw.video_settings?.resolutions?.[key]
    if (typeof value === 'boolean') merged.video_settings.resolutions[key] = value
  })
  durationOptions.forEach((key) => {
    const value = raw.video_settings?.durations?.[key]
    if (typeof value === 'boolean') merged.video_settings.durations[key] = value
  })
  promptOptions.forEach(({ key }) => {
    const value = raw.prompts?.[key]
    if (typeof value === 'string') merged.prompts[key] = value
  })
  return merged
}

const applyResponse = (payload: QqccBotConfigResponse) => {
  Object.assign(config, mergeConfig(payload.config))
  configKey.value = payload.key || ''
  updatedAt.value = payload.updated_at || null
}

const buildPayload = (): QqccBotConfig => JSON.parse(JSON.stringify(config))

const loadConfig = async () => {
  loading.value = true
  try {
    const payload = await fetchQqccBotConfig()
    applyResponse(payload)
  } catch {
    message.error('加载懒人Bot配置失败')
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  saving.value = true
  try {
    const saved = await updateQqccBotConfig(buildPayload())
    applyResponse(saved)
    message.success('懒人Bot配置已保存')
  } catch {
    message.error('保存懒人Bot配置失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadConfig()
})
</script>

<template>
  <div class="qqcc-bot-settings flex-1 flex flex-col gap-5">
    <section class="rounded-lg border border-slate-200 bg-white p-5">
      <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-semibold text-slate-900">懒人Bot配置</h2>
          <div class="mt-1 text-sm text-slate-500">
            状态：{{ statusText }} · 更新时间：{{ updatedAtText }}
          </div>
        </div>
        <div class="flex items-center gap-2">
          <a-button :loading="loading" @click="loadConfig">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
          <a-button type="primary" :loading="saving" @click="saveConfig">
            <template #icon><SaveOutlined /></template>
            保存
          </a-button>
        </div>
      </div>

      <a-spin :spinning="loading">
        <div class="grid gap-5 xl:grid-cols-[280px_1fr]">
          <div class="rounded-lg border border-slate-200 p-4">
            <div class="mb-4 flex items-center justify-between gap-3">
              <span class="text-sm font-medium text-slate-700">全局开关</span>
              <a-switch v-model:checked="config.global_enabled" data-testid="global-enabled" />
            </div>
            <div class="text-xs text-slate-400">Key：{{ configKey || '-' }}</div>
          </div>

          <div class="grid gap-4 lg:grid-cols-3">
            <section class="rounded-lg border border-slate-200 p-4">
              <h3 class="mb-3 text-sm font-semibold text-slate-800">主菜单</h3>
              <div class="space-y-3">
                <div
                  v-for="item in mainButtonOptions"
                  :key="item.key"
                  class="flex items-center justify-between gap-3"
                >
                  <span class="text-sm text-slate-700">{{ item.label }}</span>
                  <a-switch v-model:checked="config.main_buttons[item.key]" />
                </div>
              </div>
            </section>

            <section class="rounded-lg border border-slate-200 p-4">
              <h3 class="mb-3 text-sm font-semibold text-slate-800">懒人P图</h3>
              <div class="space-y-3">
                <div
                  v-for="item in photoButtonOptions"
                  :key="item.key"
                  class="flex items-center justify-between gap-3"
                >
                  <span class="text-sm text-slate-700">{{ item.label }}</span>
                  <a-switch v-model:checked="config.photo_buttons[item.key]" />
                </div>
              </div>
            </section>

            <section class="rounded-lg border border-slate-200 p-4">
              <h3 class="mb-3 text-sm font-semibold text-slate-800">脱衣方式</h3>
              <div class="space-y-3">
                <div
                  v-for="item in undressMethodOptions"
                  :key="item.key"
                  class="flex items-center justify-between gap-3"
                >
                  <span class="text-sm text-slate-700">{{ item.label }}</span>
                  <a-switch v-model:checked="config.undress_methods[item.key]" />
                </div>
              </div>
            </section>
          </div>
        </div>
      </a-spin>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-5">
      <div class="grid gap-5 xl:grid-cols-[1fr_320px]">
        <div>
          <h3 class="mb-4 text-sm font-semibold text-slate-800">AI动图场景</h3>
          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <div
              v-for="item in videoButtonOptions"
              :key="item.key"
              class="flex min-h-12 items-center justify-between gap-3 rounded-lg border border-slate-200 px-4"
            >
              <span class="text-sm text-slate-700">{{ item.label }}</span>
              <a-switch v-model:checked="config.video_buttons[item.key]" />
            </div>
          </div>
        </div>

        <div class="rounded-lg border border-slate-200 p-4">
          <h3 class="mb-4 text-sm font-semibold text-slate-800">画质与时长</h3>
          <div class="mb-4">
            <div class="mb-2 text-xs font-medium text-slate-500">画质</div>
            <div class="flex flex-wrap gap-2">
              <a-checkbox
                v-for="item in resolutionOptions"
                :key="item"
                v-model:checked="config.video_settings.resolutions[item]"
              >
                {{ item }}
              </a-checkbox>
            </div>
          </div>
          <div>
            <div class="mb-2 text-xs font-medium text-slate-500">时长</div>
            <div class="flex flex-wrap gap-2">
              <a-checkbox
                v-for="item in durationOptions"
                :key="item"
                v-model:checked="config.video_settings.durations[item]"
              >
                {{ item }}
              </a-checkbox>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-5">
      <h3 class="mb-4 text-sm font-semibold text-slate-800">提示词覆盖</h3>
      <div class="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <a-form-item v-for="item in promptOptions" :key="item.key" :label="item.label">
          <a-textarea
            v-model:value="config.prompts[item.key]"
            :rows="5"
            placeholder="留空使用 prompts.ini"
          />
        </a-form-item>
      </div>
    </section>
  </div>
</template>
