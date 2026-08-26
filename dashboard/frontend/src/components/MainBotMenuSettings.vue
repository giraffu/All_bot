<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import message from 'ant-design-vue/es/message'

import {
  fetchFeatureEntryVisibilityConfig,
  fetchMainBotMenuConfig,
  updateFeatureEntryVisibilityConfig,
  updateMainBotMenuConfig,
} from '../api/api'

interface MenuItemConfig {
  key: string
  visible: boolean
}

interface MainMenuConfig {
  buttons_per_row: number
  items: MenuItemConfig[]
}

interface MainBotMenuConfig {
  main_menu: MainMenuConfig
  submenus: Record<string, MenuItemConfig[]>
}

interface MainBotMenuConfigResponse {
  key: string
  config: MainBotMenuConfig
  updated_at?: string | null
}

interface FeatureEntryVisibilityConfig {
  web: {
    edit: boolean
    edit_v2_5: boolean
    edit_v3: boolean
    txt2img: boolean
    i2i_pro: boolean
    custom_video: boolean
    face_swap: boolean
    random_faceswap: boolean
    ltx_video: boolean
    ltx_video_v2: boolean
    ltx_t2v: boolean
    minimax_h3: boolean
    wan22_video_v2: boolean
    scail2_action_transfer: boolean
    scail2_video_replacement: boolean
    scail2_face_swap_v2: boolean
    character_assets: boolean
  }
  gallery: {
    txt2img: boolean
    i2i_pro: boolean
    edit: boolean
    free_edit_v2_5: boolean
    free_edit_v3: boolean
    custom_video: boolean
    ltx_video: boolean
    minimax_h3: boolean
    wan22_video_v2: boolean
    scail2_action_transfer: boolean
    scail2_video_replacement: boolean
    scail2_face_swap_v2: boolean
  }
  advanced_video_pro: Record<AdvancedVideoProMode, AdvancedVideoProModeConfig>
}

type AdvancedVideoProMode = 't2v' | 'i2v' | 'flf2v' | 'ref2v'

interface AdvancedVideoProModeConfig {
  main_model: string
  addon_items: AdvancedVideoProAddonItem[]
}

interface AdvancedVideoProAddonItem {
  name: string
  strength: number
}

interface SelectOption {
  value: string
  label: string
}

interface AdvancedVideoProOptions {
  modes: Array<SelectOption & { value: AdvancedVideoProMode }>
  main_models: Record<AdvancedVideoProMode, SelectOption[]>
  addon_models: Array<SelectOption & {
    supported_modes: AdvancedVideoProMode[]
    default_strength: number
  }>
  max_addon_items: number
  strength_min: number
  strength_max: number
}

interface FeatureEntryVisibilityConfigResponse {
  key: string
  config: FeatureEntryVisibilityConfig
  options?: AdvancedVideoProOptions
  updated_at?: string | null
}

const MENU_LABELS: Record<string, string> = {
  'menu.lazy_bot': '懒人bot',
  'menu.recharge': '充值灵石',
  'menu.checkin': '每日签到',
  'menu.profile': '个人中心',
  'menu.share': '分享赚灵石',
  'menu.queue': '排队状态',
  'menu.switch_lang': '语言切换',
  'menu.photo_edit': '图片换脸',
  'menu.video_to_video': '视频生视频',
  'menu.txt2img': '文生图',
  'menu.i2i_pro': '幻想换脸',
  'menu.free_edit': '自由P图',
  'menu.video_lora': '图生视频',
  'menu.ltx_video': '高级图生视频',
  'menu.advanced_video_pro': '高级图生视频 Pro',
  'menu.wan22_video_v2': '图生视频v2',
  'menu.photo_edit_faceswap': '快速换脸',
  'menu.photo_edit_random_faceswap': '随机换脸',
  'menu.video_to_video_replacement': '视频换人',
  'menu.video_to_video_action_transfer': '动作迁移',
  'menu.face_video': '视频换脸',
}

const SUBMENU_TITLES: Record<string, string> = {
  'menu.photo_edit': '图片换脸 · 二级菜单',
  'menu.video_to_video': '视频生视频 · 二级菜单',
}

const emptyConfig = (): MainBotMenuConfig => ({
  main_menu: { buttons_per_row: 3, items: [] },
  submenus: {},
})

const emptyEntryConfig = (): FeatureEntryVisibilityConfig => ({
  web: {
    edit: true,
    edit_v2_5: true,
    edit_v3: true,
    txt2img: true,
    i2i_pro: true,
    custom_video: true,
    face_swap: true,
    random_faceswap: true,
    ltx_video: true,
    ltx_video_v2: true,
    ltx_t2v: true,
    minimax_h3: false,
    wan22_video_v2: true,
    scail2_action_transfer: true,
    scail2_video_replacement: true,
    scail2_face_swap_v2: true,
    character_assets: false,
  },
  gallery: {
    txt2img: true,
    i2i_pro: true,
    edit: true,
    free_edit_v2_5: true,
    free_edit_v3: true,
    custom_video: true,
    ltx_video: true,
    minimax_h3: false,
    wan22_video_v2: true,
    scail2_action_transfer: true,
    scail2_video_replacement: true,
    scail2_face_swap_v2: true,
  },
  advanced_video_pro: {
    t2v: { main_model: '10eros', addon_items: [] },
    i2v: { main_model: '10eros', addon_items: [] },
    flf2v: { main_model: '10eros', addon_items: [] },
    ref2v: { main_model: '10eros', addon_items: [] },
  },
})

const emptyAdvancedVideoProOptions = (): AdvancedVideoProOptions => ({
  modes: [
    { value: 't2v', label: '文生视频' },
    { value: 'i2v', label: '首帧图生视频' },
    { value: 'flf2v', label: '首尾帧视频' },
    { value: 'ref2v', label: '参考图生视频' },
  ],
  main_models: {
    t2v: [{ value: '10eros', label: '10Eros TURBO' }],
    i2v: [{ value: '10eros', label: '10Eros TURBO' }],
    flf2v: [{ value: '10eros', label: '10Eros TURBO' }],
    ref2v: [{ value: '10eros', label: '10Eros TURBO' }],
  },
  addon_models: [],
  max_addon_items: 13,
  strength_min: 0.1,
  strength_max: 2,
})

const WEB_ENTRY_OPTIONS = [
  { key: 'edit', label: '自由P图', description: '基础自由编辑工作台' },
  { key: 'edit_v2_5', label: '自由P图 v2.5', description: '一至两张图片自由编辑' },
  { key: 'edit_v3', label: '自由P图 v3', description: '新一代单图自由编辑' },
  { key: 'txt2img', label: '文生图', description: '文字生成图片' },
  { key: 'i2i_pro', label: '幻想换脸', description: '图片与提示词生成' },
  { key: 'face_swap', label: '快速换脸', description: '双图人脸替换' },
  { key: 'random_faceswap', label: '随机换脸', description: '单图随机模板换脸' },
  { key: 'character_assets', label: '人物角色图', description: '人物资产创建和入口' },
  { key: 'custom_video', label: '图生视频', description: '原图生视频工作台' },
  { key: 'wan22_video_v2', label: '图生视频 v2', description: 'Wan 2.2 图生视频' },
  { key: 'ltx_video', label: '高级图生视频', description: '原高级图生视频入口' },
  { key: 'ltx_video_v2', label: '高级图生视频 v2', description: 'LTX v2 工作台入口' },
  { key: 'ltx_t2v', label: '高级文生视频', description: 'LTX 文生视频入口' },
  { key: 'minimax_h3', label: '高级图生视频 Pro', description: 'MiniMax H3 Pro 工作台' },
  { key: 'scail2_action_transfer', label: '动作迁移', description: '参考动作迁移到人物' },
  { key: 'scail2_video_replacement', label: '视频换人', description: '替换视频中的人物' },
  { key: 'scail2_face_swap_v2', label: '视频换脸', description: '新版视频换脸工作台' },
] as const satisfies ReadonlyArray<{
  key: keyof FeatureEntryVisibilityConfig['web']
  label: string
  description: string
}>

const GALLERY_ENTRY_OPTIONS = [
  { key: 'txt2img', label: '文生图' },
  { key: 'i2i_pro', label: '幻想换脸' },
  { key: 'edit', label: '自由P图 / 图生图附加模型' },
  { key: 'free_edit_v2_5', label: '自由P图 v2.5' },
  { key: 'free_edit_v3', label: '自由P图 v3' },
  { key: 'custom_video', label: '图生视频' },
  { key: 'ltx_video', label: '高级图生视频' },
  { key: 'minimax_h3', label: '高级图生视频 Pro' },
  { key: 'wan22_video_v2', label: '图生视频 v2' },
  { key: 'scail2_action_transfer', label: '动作迁移' },
  { key: 'scail2_video_replacement', label: '视频换人' },
  { key: 'scail2_face_swap_v2', label: '视频换脸' },
] as const satisfies ReadonlyArray<{
  key: keyof FeatureEntryVisibilityConfig['gallery']
  label: string
}>

type EntryScope = 'web' | 'bot' | 'gallery' | 'models'

const ENTRY_SCOPE_TABS: ReadonlyArray<{ key: EntryScope; label: string }> = [
  { key: 'web', label: 'Web 端' },
  { key: 'bot', label: '主 Bot' },
  { key: 'gallery', label: '修仙市集' },
  { key: 'models', label: 'Pro 模型预设' },
]

const loading = ref(false)
const saving = ref(false)
const entryLoading = ref(false)
const entrySaving = ref(false)
const updatedAt = ref<string | null>(null)
const entryUpdatedAt = ref<string | null>(null)
const config = ref<MainBotMenuConfig>(emptyConfig())
const entryConfig = ref<FeatureEntryVisibilityConfig>(emptyEntryConfig())
const advancedVideoProOptions = ref<AdvancedVideoProOptions>(
  emptyAdvancedVideoProOptions(),
)
const activeScope = ref<EntryScope>('web')

const visibleMainCount = computed(() =>
  config.value.main_menu.items.filter((item) => item.visible).length
)

const cloneConfig = (value: MainBotMenuConfig): MainBotMenuConfig => ({
  main_menu: {
    buttons_per_row: Number(value.main_menu.buttons_per_row),
    items: value.main_menu.items.map((item) => ({ ...item })),
  },
  submenus: Object.fromEntries(
    Object.entries(value.submenus).map(([key, items]) => [
      key,
      items.map((item) => ({ ...item })),
    ])
  ),
})

const cloneEntryConfig = (
  value: FeatureEntryVisibilityConfig,
): FeatureEntryVisibilityConfig => ({
  web: { ...value.web },
  gallery: { ...value.gallery },
  advanced_video_pro: Object.fromEntries(
    Object.entries(value.advanced_video_pro).map(([mode, profile]) => [
      mode,
      {
        main_model: profile.main_model,
        addon_items: profile.addon_items.map(item => ({ ...item })),
      },
    ]),
  ) as FeatureEntryVisibilityConfig['advanced_video_pro'],
})

const testIdKey = (key: string) => key.replaceAll('.', '-')
const labelFor = (key: string) => MENU_LABELS[key] ?? key

const formatUpdatedAt = (value: string | null) => {
  if (!value) return '尚未保存运行时配置'
  return `最后保存：${new Date(value).toLocaleString('zh-CN')}`
}

const applyResponse = (payload: MainBotMenuConfigResponse) => {
  config.value = cloneConfig(payload.config)
  updatedAt.value = payload.updated_at ?? null
}

const applyEntryResponse = (payload: FeatureEntryVisibilityConfigResponse) => {
  entryConfig.value = cloneEntryConfig(payload.config)
  if (payload.options) advancedVideoProOptions.value = payload.options
  entryUpdatedAt.value = payload.updated_at ?? null
}

const addonOptionsForMode = (mode: AdvancedVideoProMode) => (
  advancedVideoProOptions.value.addon_models.filter(option => (
    option.supported_modes.includes(mode)
  ))
)

const selectedAddonNamesForMode = (mode: AdvancedVideoProMode) => (
  entryConfig.value.advanced_video_pro[mode].addon_items.map(item => item.name)
)

const addonLabel = (name: string) => (
  advancedVideoProOptions.value.addon_models.find(option => option.value === name)?.label
  ?? name
)

const updateAddonSelection = (mode: AdvancedVideoProMode, event: Event) => {
  const target = event.target as HTMLSelectElement
  const selectedNames = Array.from(target.selectedOptions)
    .map(option => option.value)
    .slice(0, advancedVideoProOptions.value.max_addon_items)
  const profile = entryConfig.value.advanced_video_pro[mode]
  const existing = new Map(profile.addon_items.map(item => [item.name, item]))
  const optionByName = new Map(
    addonOptionsForMode(mode).map(option => [option.value, option]),
  )
  profile.addon_items = selectedNames.map(name => ({
    name,
    strength: existing.get(name)?.strength
      ?? optionByName.get(name)?.default_strength
      ?? 1,
  }))
}

const hasInvalidAddonStrength = computed(() => (
  Object.values(entryConfig.value.advanced_video_pro).some(profile => (
    profile.addon_items.some(item => (
      !Number.isFinite(item.strength)
      || item.strength < advancedVideoProOptions.value.strength_min
      || item.strength > advancedVideoProOptions.value.strength_max
    ))
  ))
))

const loadConfig = async () => {
  loading.value = true
  try {
    applyResponse(await fetchMainBotMenuConfig())
  } catch {
    message.error('加载主 Bot 菜单配置失败')
  } finally {
    loading.value = false
  }
}

const loadEntryConfig = async () => {
  entryLoading.value = true
  try {
    applyEntryResponse(await fetchFeatureEntryVisibilityConfig())
  } catch {
    message.error('加载 Web 与修仙市集入口配置失败')
  } finally {
    entryLoading.value = false
  }
}

const reloadAll = async () => {
  await Promise.all([loadEntryConfig(), loadConfig()])
}

const moveMainItem = (index: number, offset: -1 | 1) => {
  const target = index + offset
  const items = config.value.main_menu.items
  if (target < 0 || target >= items.length) return
  ;[items[index], items[target]] = [items[target], items[index]]
}

const saveConfig = async () => {
  if (visibleMainCount.value === 0) {
    message.error('主菜单至少需要保留一个可见按钮')
    return
  }
  saving.value = true
  try {
    const saved = await updateMainBotMenuConfig(cloneConfig(config.value))
    applyResponse(saved)
    message.success('主 Bot 菜单配置已保存')
  } catch {
    message.error('保存主 Bot 菜单配置失败')
  } finally {
    saving.value = false
  }
}

const saveEntryConfig = async (scope: 'web' | 'gallery' | 'models') => {
  if (scope === 'models' && hasInvalidAddonStrength.value) {
    message.error(
      `附加模型强度必须在 ${advancedVideoProOptions.value.strength_min}–${advancedVideoProOptions.value.strength_max} 之间`,
    )
    return
  }
  entrySaving.value = true
  try {
    const saved = await updateFeatureEntryVisibilityConfig(
      cloneEntryConfig(entryConfig.value),
    )
    applyEntryResponse(saved)
    const successMessages = {
      web: 'Web 端入口配置已保存',
      gallery: '修仙市集入口配置已保存',
      models: 'Pro 模型预设已保存',
    }
    message.success(successMessages[scope])
  } catch {
    const errorMessages = {
      web: '保存 Web 端入口配置失败',
      gallery: '保存修仙市集入口配置失败',
      models: '保存 Pro 模型预设失败',
    }
    message.error(errorMessages[scope])
  } finally {
    entrySaving.value = false
  }
}

onMounted(() => {
  void reloadAll()
})
</script>

<template>
  <div class="main-bot-menu-settings flex flex-1 flex-col gap-5">
    <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="header-row">
        <div>
          <h2 class="text-lg font-semibold text-slate-950">入口与菜单控制</h2>
          <p class="mt-1 text-sm text-slate-500">
            分别管理 Web、主 Bot、修仙市集入口与 Pro 模型预设；不会停用任务、旧按钮、深链或文字命令。
          </p>
        </div>
        <div class="toolbar">
          <button
            type="button"
            class="secondary-button"
            :disabled="loading || entryLoading"
            @click="reloadAll"
          >
            {{ loading || entryLoading ? '刷新中…' : '全部刷新' }}
          </button>
        </div>
      </div>
      <nav class="scope-tabs" aria-label="入口控制范围">
        <button
          v-for="tab in ENTRY_SCOPE_TABS"
          :key="tab.key"
          type="button"
          class="scope-tab"
          :class="{ 'is-active': activeScope === tab.key }"
          :data-testid="`scope-tab-${tab.key}`"
          @click="activeScope = tab.key"
        >
          {{ tab.label }}
        </button>
      </nav>
    </section>

    <section
      v-if="activeScope === 'web'"
      data-testid="web-entry-panel"
      class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div class="section-heading">
        <div>
          <h3 class="text-base font-semibold text-slate-900">Web 端入口</h3>
          <p class="mt-1 text-sm text-slate-500">用户刷新或重新打开 Web 后读取最新配置。</p>
          <p class="mt-1 text-xs text-slate-400">{{ formatUpdatedAt(entryUpdatedAt) }}</p>
        </div>
        <button
          type="button"
          class="primary-button"
          data-testid="save-web-entry-visibility"
          :disabled="entrySaving || entryLoading"
          @click="saveEntryConfig('web')"
        >
          {{ entrySaving ? '保存中…' : '保存 Web 端' }}
        </button>
      </div>

      <p class="mt-4 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
        开关只控制练功房功能入口；能力未发布时即使设为可见也不会开放，历史记录和模板深链不受影响。
      </p>

      <div class="web-entry-grid">
        <div v-for="item in WEB_ENTRY_OPTIONS" :key="item.key" class="submenu-item">
          <div>
            <div class="text-sm font-medium text-slate-800">{{ item.label }}</div>
            <div class="text-xs text-slate-400">{{ item.description }}</div>
          </div>
          <div class="menu-actions">
            <span class="visibility-tag" :class="entryConfig.web[item.key] ? 'is-visible' : 'is-hidden'">
              {{ entryConfig.web[item.key] ? '可见' : '隐藏' }}
            </span>
            <label class="visibility-switch">
              <input
                v-model="entryConfig.web[item.key]"
                type="checkbox"
                :data-testid="`entry-web-${item.key}`"
              />
              <span class="switch-track" aria-hidden="true"></span>
            </label>
          </div>
        </div>
      </div>
    </section>

    <section
      v-if="activeScope === 'models'"
      data-testid="advanced-video-pro-panel"
      class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div class="section-heading">
        <div>
          <h3 class="text-base font-semibold text-slate-900">高级图生视频 Pro 模型预设</h3>
          <p class="mt-1 text-sm text-slate-500">
            主 Bot 与 Web 的新任务统一使用这里的主模型、附加模型与强度；用户只选择时长、清晰度和比例。
          </p>
          <p class="mt-1 text-xs text-slate-400">{{ formatUpdatedAt(entryUpdatedAt) }}</p>
        </div>
        <button
          type="button"
          class="primary-button"
          data-testid="save-advanced-video-pro-config"
          :disabled="entrySaving || entryLoading"
          @click="saveEntryConfig('models')"
        >
          {{ entrySaving ? '保存中…' : '保存模型预设' }}
        </button>
      </div>

      <p class="mt-4 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        每种模式最多选择 {{ advancedVideoProOptions.max_addon_items }} 个附加模型；强度范围为
        {{ advancedVideoProOptions.strength_min }}–{{ advancedVideoProOptions.strength_max }}。
      </p>

      <div class="advanced-video-pro-grid mt-4">
        <article
          v-for="modeOption in advancedVideoProOptions.modes"
          :key="modeOption.value"
          class="advanced-video-pro-card"
        >
          <h4 class="text-sm font-semibold text-slate-800">{{ modeOption.label }}</h4>
          <label class="config-field mt-3">
            <span>主模型</span>
            <select
              v-model="entryConfig.advanced_video_pro[modeOption.value].main_model"
              :data-testid="`avp-main-model-${modeOption.value}`"
            >
              <option
                v-for="option in advancedVideoProOptions.main_models[modeOption.value]"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </label>
          <label class="config-field mt-3">
            <span>附加模型（可多选）</span>
            <select
              multiple
              size="7"
              :value="selectedAddonNamesForMode(modeOption.value)"
              :data-testid="`avp-addon-models-${modeOption.value}`"
              @change="updateAddonSelection(modeOption.value, $event)"
            >
              <option
                v-for="option in addonOptionsForMode(modeOption.value)"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}（默认 {{ option.default_strength }}）
              </option>
            </select>
          </label>
          <div
            v-if="entryConfig.advanced_video_pro[modeOption.value].addon_items.length"
            class="selected-addon-list mt-3"
          >
            <div class="text-xs font-semibold text-slate-600">已选模型强度</div>
            <label
              v-for="item in entryConfig.advanced_video_pro[modeOption.value].addon_items"
              :key="item.name"
              class="addon-strength-row"
            >
              <span>{{ addonLabel(item.name) }}</span>
              <input
                v-model.number="item.strength"
                type="number"
                :min="advancedVideoProOptions.strength_min"
                :max="advancedVideoProOptions.strength_max"
                step="0.05"
                :data-testid="`avp-addon-strength-${modeOption.value}-${item.name}`"
              />
            </label>
          </div>
          <p v-else class="mt-3 text-xs text-slate-400">未选择附加模型</p>
        </article>
      </div>
    </section>

    <section
      v-if="activeScope === 'bot'"
      data-testid="bot-entry-panel"
      class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div class="section-heading">
        <div>
          <h3 class="text-base font-semibold text-slate-900">主 Bot 菜单按钮</h3>
          <p class="mt-1 text-sm text-slate-500">顺序从上到下排列，Bot 会按设置的每行数量自动换行。</p>
          <p class="mt-1 text-xs text-slate-400">{{ formatUpdatedAt(updatedAt) }}</p>
        </div>
        <div class="toolbar">
          <label class="row-size-control">
            <span>每行按钮数</span>
            <select
              v-model.number="config.main_menu.buttons_per_row"
              data-testid="buttons-per-row"
            >
              <option v-for="count in 4" :key="count" :value="count">{{ count }}</option>
            </select>
          </label>
          <button
            type="button"
            class="primary-button"
            data-testid="save-main-bot-menu"
            :disabled="saving || loading"
            @click="saveConfig"
          >
            {{ saving ? '保存中…' : '保存主 Bot' }}
          </button>
        </div>
      </div>

      <div class="menu-list">
        <article
          v-for="(item, index) in config.main_menu.items"
          :key="item.key"
          class="menu-item"
        >
          <div class="menu-item-identity">
            <span class="position-index">{{ index + 1 }}</span>
            <div>
              <div class="font-medium text-slate-900">{{ labelFor(item.key) }}</div>
              <div class="text-xs text-slate-400">{{ item.key }}</div>
            </div>
          </div>
          <div class="menu-actions">
            <span
              class="visibility-tag"
              :class="item.visible ? 'is-visible' : 'is-hidden'"
              :data-testid="`status-${testIdKey(item.key)}`"
            >{{ item.visible ? '可见' : '隐藏' }}</span>
            <label class="visibility-switch">
              <input
                v-model="item.visible"
                type="checkbox"
                :data-testid="`visibility-${testIdKey(item.key)}`"
              />
              <span class="switch-track" aria-hidden="true"></span>
            </label>
            <button
              type="button"
              class="icon-button"
              :data-testid="`move-up-${testIdKey(item.key)}`"
              :disabled="index === 0"
              aria-label="上移"
              @click="moveMainItem(index, -1)"
            >↑</button>
            <button
              type="button"
              class="icon-button"
              :data-testid="`move-down-${testIdKey(item.key)}`"
              :disabled="index === config.main_menu.items.length - 1"
              aria-label="下移"
              @click="moveMainItem(index, 1)"
            >↓</button>
          </div>
        </article>
      </div>
    </section>

    <section
      v-if="activeScope === 'bot'"
      class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div class="mb-4">
        <h3 class="text-base font-semibold text-slate-900">二级菜单</h3>
        <p class="mt-1 text-sm text-slate-500">二级功能保持固定顺序，每行最多两个按钮。</p>
      </div>

      <div class="submenu-grid">
        <article
          v-for="(items, parentKey) in config.submenus"
          :key="parentKey"
          class="submenu-card"
        >
          <h4 class="font-semibold text-slate-900">{{ SUBMENU_TITLES[parentKey] ?? parentKey }}</h4>
          <div class="mt-3 space-y-2">
            <div v-for="item in items" :key="item.key" class="submenu-item">
              <div>
                <div class="text-sm font-medium text-slate-800">{{ labelFor(item.key) }}</div>
                <div class="text-xs text-slate-400">{{ item.key }}</div>
              </div>
              <div class="menu-actions">
                <span
                  class="visibility-tag"
                  :class="item.visible ? 'is-visible' : 'is-hidden'"
                  :data-testid="`status-${testIdKey(item.key)}`"
                >{{ item.visible ? '可见' : '隐藏' }}</span>
                <label class="visibility-switch">
                  <input
                    v-model="item.visible"
                    type="checkbox"
                    :data-testid="`visibility-${testIdKey(item.key)}`"
                  />
                  <span class="switch-track" aria-hidden="true"></span>
                </label>
              </div>
            </div>
            <div class="fixed-back-item">返回主菜单固定可见</div>
          </div>
        </article>
      </div>
    </section>

    <section
      v-if="activeScope === 'gallery'"
      data-testid="gallery-entry-panel"
      class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div class="section-heading">
        <div>
          <h3 class="text-base font-semibold text-slate-900">修仙市集入口</h3>
          <p class="mt-1 text-sm text-slate-500">控制市集类型筛选与分组页签，不隐藏已有作品。</p>
          <p class="mt-1 text-xs text-slate-400">{{ formatUpdatedAt(entryUpdatedAt) }}</p>
        </div>
        <button
          type="button"
          class="primary-button"
          data-testid="save-gallery-entry-visibility"
          :disabled="entrySaving || entryLoading"
          @click="saveEntryConfig('gallery')"
        >
          {{ entrySaving ? '保存中…' : '保存修仙市集' }}
        </button>
      </div>

      <div class="web-entry-grid">
        <div
          v-for="item in GALLERY_ENTRY_OPTIONS"
          :key="item.key"
          class="submenu-item"
        >
          <div>
            <div class="text-sm font-medium text-slate-800">{{ item.label }}</div>
            <div class="text-xs text-slate-400">市集类型筛选与分组页签</div>
          </div>
          <div class="menu-actions">
            <span class="visibility-tag" :class="entryConfig.gallery[item.key] ? 'is-visible' : 'is-hidden'">
              {{ entryConfig.gallery[item.key] ? '可见' : '隐藏' }}
            </span>
            <label class="visibility-switch">
              <input
                v-model="entryConfig.gallery[item.key]"
                type="checkbox"
                :data-testid="`entry-gallery-${item.key}`"
              />
              <span class="switch-track" aria-hidden="true"></span>
            </label>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.main-bot-menu-settings { min-width: 0; }
.header-row, .section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.toolbar, .menu-actions { display: flex; align-items: center; gap: .5rem; }
.scope-tabs { margin-top: 1.1rem; display: flex; gap: .35rem; overflow-x: auto; border-bottom: 1px solid #e2e8f0; }
.scope-tab { flex: 0 0 auto; border-bottom: 2px solid transparent; padding: .65rem 1.2rem; color: #64748b; font-size: .9rem; font-weight: 600; transition: .15s ease; }
.scope-tab:hover { color: #2563eb; }
.scope-tab.is-active { border-bottom-color: #2563eb; color: #1d4ed8; }
.primary-button, .secondary-button, .icon-button { border-radius: .5rem; border: 1px solid #cbd5e1; padding: .5rem .85rem; font-size: .875rem; transition: .15s ease; }
.primary-button { border-color: #2563eb; background: #2563eb; color: white; }
.secondary-button, .icon-button { background: white; color: #334155; }
button:disabled { cursor: not-allowed; opacity: .45; }
.row-size-control { display: flex; align-items: center; gap: .65rem; color: #475569; font-size: .875rem; }
.row-size-control select { border: 1px solid #cbd5e1; border-radius: .5rem; background: white; padding: .4rem 1.8rem .4rem .65rem; }
.menu-list { margin-top: 1rem; display: grid; gap: .55rem; }
.menu-item, .submenu-item { display: flex; align-items: center; justify-content: space-between; gap: 1rem; border: 1px solid #e2e8f0; border-radius: .65rem; padding: .75rem .85rem; }
.menu-item-identity { display: flex; align-items: center; gap: .75rem; min-width: 0; }
.menu-item-identity > div, .submenu-item > div { min-width: 0; }
.menu-item-identity .text-xs, .submenu-item .text-xs { overflow-wrap: anywhere; }
.position-index { display: inline-flex; width: 1.8rem; height: 1.8rem; align-items: center; justify-content: center; border-radius: 999px; background: #eff6ff; color: #2563eb; font-size: .75rem; font-weight: 700; }
.visibility-tag { border-radius: 999px; padding: .2rem .55rem; font-size: .75rem; font-weight: 600; }
.visibility-tag.is-visible { background: #dcfce7; color: #15803d; }
.visibility-tag.is-hidden { background: #f1f5f9; color: #64748b; }
.visibility-switch { position: relative; display: inline-flex; cursor: pointer; }
.visibility-switch input { position: absolute; opacity: 0; pointer-events: none; }
.switch-track { width: 2.35rem; height: 1.3rem; border-radius: 999px; background: #cbd5e1; position: relative; transition: .15s ease; }
.switch-track::after { content: ''; position: absolute; width: 1rem; height: 1rem; top: .15rem; left: .15rem; border-radius: 999px; background: white; box-shadow: 0 1px 2px rgb(15 23 42 / .25); transition: .15s ease; }
.visibility-switch input:checked + .switch-track { background: #2563eb; }
.visibility-switch input:checked + .switch-track::after { transform: translateX(1.05rem); }
.icon-button { width: 2rem; height: 2rem; padding: 0; }
.submenu-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.submenu-card { border: 1px solid #e2e8f0; border-radius: .75rem; background: #f8fafc; padding: 1rem; }
.web-entry-grid { margin-top: 1rem; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .65rem; }
.fixed-back-item { border: 1px dashed #cbd5e1; border-radius: .6rem; padding: .65rem .8rem; color: #64748b; font-size: .8rem; text-align: center; }
.advanced-video-pro-config { border: 1px solid #bfdbfe; border-radius: .75rem; background: #f8fbff; padding: 1rem; }
.advanced-video-pro-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
.advanced-video-pro-card { border: 1px solid #dbeafe; border-radius: .65rem; background: white; padding: .85rem; }
.config-field { display: flex; flex-direction: column; gap: .35rem; color: #475569; font-size: .75rem; }
.config-field select { min-width: 0; border: 1px solid #cbd5e1; border-radius: .5rem; background: white; padding: .45rem .55rem; color: #334155; }
.config-field select[multiple] { min-height: 9rem; }
.selected-addon-list { display: grid; gap: .45rem; border-top: 1px solid #e2e8f0; padding-top: .75rem; }
.addon-strength-row { display: grid; grid-template-columns: minmax(0, 1fr) 5.5rem; align-items: center; gap: .75rem; color: #475569; font-size: .75rem; }
.addon-strength-row span { overflow-wrap: anywhere; }
.addon-strength-row input { width: 100%; border: 1px solid #cbd5e1; border-radius: .45rem; padding: .4rem .5rem; color: #334155; }
@media (max-width: 760px) {
  .main-bot-menu-settings > section { padding: .75rem; }
  .header-row, .section-heading, .menu-item, .submenu-item { align-items: stretch; flex-direction: column; }
  .toolbar { width: 100%; flex-direction: column; }
  .toolbar button { width: 100%; white-space: nowrap; }
  .row-size-control { align-items: stretch; flex-direction: column; }
  .menu-item, .submenu-item { padding: .65rem; }
  .menu-actions { width: 100%; justify-content: flex-start; flex-wrap: wrap; }
  .submenu-grid { grid-template-columns: 1fr; }
  .web-entry-grid { grid-template-columns: 1fr; }
  .advanced-video-pro-grid { grid-template-columns: 1fr; }
  .scope-tab { flex: 1 0 auto; padding-inline: .8rem; text-align: center; }
}
</style>
