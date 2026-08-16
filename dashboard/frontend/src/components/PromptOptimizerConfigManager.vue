<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../api/client'

type Config = {
  scene_key: string
  display_name: string
  description: string
  system_template: string
  user_template: string
  revision: number
  content_hash: string
  template_ref: string
  config_source: 'built-in' | 'database'
  compatibility_status: 'current' | 'fallback'
  fallback_reason: 'no_saved_config' | 'incompatible_saved_config' | null
  stored_revision: number | null
}
const configs = ref<Config[]>([])
const active = ref('ltx_video_v2')
const loading = ref(false)
const refresh = async () => { configs.value = (await api.get('/api/prompt-optimizer/configs')).data; active.value ||= configs.value[0]?.scene_key }
const sourceLabel = (config: Config) => config.config_source === 'database' ? '数据库配置' : '内置默认'
const statusMessage = (config: Config) => {
  if (config.fallback_reason === 'incompatible_saved_config') {
    return `历史 revision ${config.stored_revision} 与当前模板契约不兼容；当前新任务使用内置默认配置。保存当前内容后将发布新的兼容 revision。`
  }
  if (config.fallback_reason === 'no_saved_config') {
    return '尚未保存数据库配置；当前新任务使用内置默认配置。保存后将创建 revision 1。'
  }
  return ''
}
const save = async (config: Config) => {
  loading.value = true
  try {
    const response = await api.put(`/api/prompt-optimizer/configs/${config.scene_key}`, {
      display_name: config.display_name,
      description: config.description,
      system_template: config.system_template,
      user_template: config.user_template,
    })
    configs.value = configs.value.map(item => item.scene_key === config.scene_key ? response.data : item)
    message.success(`已发布 revision ${response.data.revision}，只影响新任务`)
  } finally { loading.value = false }
}
onMounted(() => void refresh())
</script>

<template>
  <section>
    <a-alert class="mb-4" type="info" show-icon message="保存后立即用于新任务；运行中任务继续使用已入队快照。模型、价格、媒体契约和输出 Schema 不可在此修改。"/>
    <a-tabs v-model:active-key="active">
      <a-tab-pane v-for="config in configs" :key="config.scene_key" :tab="config.display_name">
        <div class="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <a-tag :color="config.config_source === 'database' ? 'green' : 'blue'">{{ sourceLabel(config) }}</a-tag>
          <span class="opacity-70">模板 {{ config.template_ref }}</span>
        </div>
        <a-alert
          v-if="statusMessage(config)"
          class="mb-4"
          :type="config.compatibility_status === 'fallback' ? 'warning' : 'info'"
          show-icon
          :message="statusMessage(config)"
        />
        <a-form layout="vertical">
          <a-form-item label="展示名称"><a-input v-model:value="config.display_name"/></a-form-item>
          <a-form-item label="说明"><a-input v-model:value="config.description"/></a-form-item>
          <a-form-item label="System Prompt"><a-textarea v-model:value="config.system_template" :rows="16"/></a-form-item>
          <a-form-item label="User Prompt"><a-textarea v-model:value="config.user_template" :rows="8"/></a-form-item>
          <div class="flex items-center justify-between"><span class="text-xs opacity-60">revision {{ config.revision }} · {{ config.content_hash.slice(0, 12) }}</span><a-button type="primary" :loading="loading" @click="save(config)">保存并立即启用</a-button></div>
        </a-form>
      </a-tab-pane>
    </a-tabs>
  </section>
</template>
