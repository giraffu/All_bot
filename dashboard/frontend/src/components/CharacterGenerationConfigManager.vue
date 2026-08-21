<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../api/client'

type GenderTemplate = 'neutral' | 'female' | 'male'
type TagGroup = 'breast_size' | 'pubic_hair' | 'skin_tone'
type CharacterViewConfig = {
  view_type: string
  display_name: string
  index: number
  required: boolean
  prompt_templates: Record<GenderTemplate, string>
  tag_groups: TagGroup[]
  tag_options: Record<TagGroup, Record<string, string>>
  revision: number
  content_hash: string
  config_source: 'built-in' | 'database'
}

const configs = ref<CharacterViewConfig[]>([])
const active = ref('face_front')
const loading = ref(false)
const groupLabels: Record<TagGroup, string> = {
  breast_size: '乳房',
  pubic_hair: '阴毛',
  skin_tone: '肤色',
}
const templateLabels: Record<GenderTemplate, string> = {
  neutral: '旧人物 / 中性提示词',
  female: '女性提示词',
  male: '男性提示词',
}
const activeConfig = computed(() => configs.value.find(item => item.view_type === active.value))

const refresh = async () => {
  configs.value = (await api.get('/api/character-generation/configs')).data
  if (!configs.value.some(item => item.view_type === active.value)) {
    active.value = configs.value[0]?.view_type ?? ''
  }
}

const save = async (config: CharacterViewConfig) => {
  loading.value = true
  try {
    const response = await api.put(`/api/character-generation/configs/${config.view_type}`, {
      display_name: config.display_name,
      prompt_templates: config.prompt_templates,
      tag_groups: config.tag_groups,
      tag_options: config.tag_options,
    })
    configs.value = configs.value.map(item => item.view_type === config.view_type ? response.data : item)
    message.success(`已发布 revision ${response.data.revision}，新建及刷新的人物工作台立即使用`)
  } finally {
    loading.value = false
  }
}

onMounted(() => void refresh())
</script>

<template>
  <section>
    <a-alert
      class="mb-4"
      type="info"
      show-icon
      message="可编辑每张人物子图的名称、男女提示词和实际生效的标签组合。{tags} 会替换为用户在该子图下选择的标签片段。"
    />
    <a-tabs v-model:active-key="active" tab-position="left">
      <a-tab-pane v-for="config in configs" :key="config.view_type" :tab="config.display_name" />
    </a-tabs>

    <a-form v-if="activeConfig" layout="vertical" class="mt-4 max-w-5xl">
      <div class="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <a-tag :color="activeConfig.config_source === 'database' ? 'green' : 'blue'">
          {{ activeConfig.config_source === 'database' ? '数据库配置' : '内置默认' }}
        </a-tag>
        <a-tag v-if="activeConfig.required" color="orange">四图必需</a-tag>
        <span class="opacity-60">{{ activeConfig.view_type }} · revision {{ activeConfig.revision }}</span>
      </div>

      <a-form-item label="子图展示名称">
        <a-input v-model:value="activeConfig.display_name" />
      </a-form-item>
      <a-form-item label="此子图生效的标签组">
        <a-checkbox-group v-model:value="activeConfig.tag_groups">
          <a-checkbox v-for="(label, key) in groupLabels" :key="key" :value="key">{{ label }}</a-checkbox>
        </a-checkbox-group>
      </a-form-item>

      <a-collapse class="mb-5">
        <a-collapse-panel v-for="group in activeConfig.tag_groups" :key="group" :header="`${groupLabels[group]}标签提示词片段`">
          <a-form-item v-for="(_, option) in activeConfig.tag_options[group]" :key="option" :label="String(option)">
            <a-input v-model:value="activeConfig.tag_options[group][option]" />
          </a-form-item>
        </a-collapse-panel>
      </a-collapse>

      <a-form-item v-for="(label, gender) in templateLabels" :key="gender" :label="label">
        <a-textarea v-model:value="activeConfig.prompt_templates[gender]" :rows="7" />
      </a-form-item>
      <div class="flex items-center justify-between">
        <span class="text-xs opacity-60">哈希 {{ activeConfig.content_hash.slice(0, 12) }}</span>
        <a-button type="primary" :loading="loading" @click="save(activeConfig)">保存并立即启用</a-button>
      </div>
    </a-form>
  </section>
</template>
