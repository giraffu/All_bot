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
    ltx_video: boolean
    minimax_h3: boolean
    character_assets: boolean
  }
  gallery: {
    minimax_h3: boolean
  }
}

interface FeatureEntryVisibilityConfigResponse {
  key: string
  config: FeatureEntryVisibilityConfig
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
    ltx_video: true,
    minimax_h3: false,
    character_assets: false,
  },
  gallery: { minimax_h3: false },
})

const WEB_ENTRY_OPTIONS = [
  { key: 'ltx_video' as const, label: '高级图生视频', description: 'Web 练功房中的原高级图生视频入口' },
  { key: 'minimax_h3' as const, label: '高级图生视频 Pro', description: 'Web 练功房中的 Pro 工作台入口' },
  { key: 'character_assets' as const, label: '人物角色图', description: 'Web 练功房和人物资产导航入口' },
]

const loading = ref(false)
const saving = ref(false)
const entryLoading = ref(false)
const entrySaving = ref(false)
const updatedAt = ref<string | null>(null)
const entryUpdatedAt = ref<string | null>(null)
const config = ref<MainBotMenuConfig>(emptyConfig())
const entryConfig = ref<FeatureEntryVisibilityConfig>(emptyEntryConfig())

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
  entryUpdatedAt.value = payload.updated_at ?? null
}

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

const saveEntryConfig = async () => {
  entrySaving.value = true
  try {
    const saved = await updateFeatureEntryVisibilityConfig(
      cloneEntryConfig(entryConfig.value),
    )
    applyEntryResponse(saved)
    message.success('Web 与修仙市集入口配置已保存')
  } catch {
    message.error('保存 Web 与修仙市集入口配置失败')
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
            分别管理 Web、修仙市集和主 Bot 的展示入口；不会停用任务、旧按钮、深链或文字命令。
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
    </section>

    <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="section-heading">
        <div>
          <h3 class="text-base font-semibold text-slate-900">Web 端入口</h3>
          <p class="mt-1 text-sm text-slate-500">用户刷新或重新打开 Web 后读取最新配置。</p>
          <p class="mt-1 text-xs text-slate-400">{{ formatUpdatedAt(entryUpdatedAt) }}</p>
        </div>
        <button
          type="button"
          class="primary-button"
          data-testid="save-feature-entry-visibility"
          :disabled="entrySaving || entryLoading"
          @click="saveEntryConfig"
        >
          {{ entrySaving ? '保存中…' : '保存 Web / 市集' }}
        </button>
      </div>

      <div class="entry-scope-grid">
        <article class="entry-scope-card">
          <h4 class="font-semibold text-slate-900">Web 端入口</h4>
          <p class="mt-1 text-xs text-slate-500">控制练功房及对应导航卡片。</p>
          <div class="mt-3 space-y-2">
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
        </article>

        <article class="entry-scope-card">
          <h4 class="font-semibold text-slate-900">修仙市集入口</h4>
          <p class="mt-1 text-xs text-slate-500">只控制市集筛选入口，不隐藏已有作品。</p>
          <div class="mt-3 space-y-2">
            <div class="submenu-item">
              <div>
                <div class="text-sm font-medium text-slate-800">高级图生视频 Pro</div>
                <div class="text-xs text-slate-400">市集类型筛选与分组页签</div>
              </div>
              <div class="menu-actions">
                <span class="visibility-tag" :class="entryConfig.gallery.minimax_h3 ? 'is-visible' : 'is-hidden'">
                  {{ entryConfig.gallery.minimax_h3 ? '可见' : '隐藏' }}
                </span>
                <label class="visibility-switch">
                  <input
                    v-model="entryConfig.gallery.minimax_h3"
                    type="checkbox"
                    data-testid="entry-gallery-minimax_h3"
                  />
                  <span class="switch-track" aria-hidden="true"></span>
                </label>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
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

    <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
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
  </div>
</template>

<style scoped>
.main-bot-menu-settings { min-width: 0; }
.header-row, .section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.toolbar, .menu-actions { display: flex; align-items: center; gap: .5rem; }
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
.entry-scope-grid { margin-top: 1rem; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.entry-scope-card { border: 1px solid #dbeafe; border-radius: .75rem; background: #f8fbff; padding: 1rem; }
.fixed-back-item { border: 1px dashed #cbd5e1; border-radius: .6rem; padding: .65rem .8rem; color: #64748b; font-size: .8rem; text-align: center; }
@media (max-width: 760px) {
  .main-bot-menu-settings > section { padding: .75rem; }
  .header-row, .section-heading, .menu-item, .submenu-item { align-items: stretch; flex-direction: column; }
  .toolbar { width: 100%; flex-direction: column; }
  .toolbar button { width: 100%; white-space: nowrap; }
  .row-size-control { align-items: stretch; flex-direction: column; }
  .menu-item, .submenu-item { padding: .65rem; }
  .menu-actions { width: 100%; justify-content: flex-start; flex-wrap: wrap; }
  .submenu-grid { grid-template-columns: 1fr; }
  .entry-scope-grid { grid-template-columns: 1fr; }
}
</style>
