<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../api/client'

type GenderTemplate = 'neutral' | 'female' | 'male'
type TagGroup = 'breast_size' | 'pubic_hair' | 'skin_tone'
type DetailViewType = 'torso_front' | 'genitals_front' | 'pelvis_back'
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
type CharacterViewImageTemplate = {
  id: string
  view_type: DetailViewType
  name: string
  gender: GenderTemplate
  sort_order: number
  status: 'active' | 'disabled'
  preview_url: string
}

const configs = ref<CharacterViewConfig[]>([])
const templates = ref<CharacterViewImageTemplate[]>([])
const active = ref('face_front')
const section = ref<'prompts' | 'templates'>('prompts')
const loading = ref(false)
const uploadFile = ref<File | null>(null)
const uploadPreview = ref<string | null>(null)
const templateForm = reactive({
  view_type: 'torso_front' as DetailViewType,
  name: '',
  gender: 'neutral' as GenderTemplate,
  sort_order: 0,
})
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
const viewLabels: Record<DetailViewType, string> = {
  torso_front: '胸部镜头',
  genitals_front: '正面私处',
  pelvis_back: '背面私处',
}
const genderLabels: Record<GenderTemplate, string> = {
  neutral: '中性',
  female: '女性',
  male: '男性',
}
const activeConfig = computed(() => configs.value.find(item => item.view_type === active.value))
const groupedTemplates = computed(() => Object.fromEntries(
  (Object.keys(viewLabels) as DetailViewType[]).map(viewType => [
    viewType,
    templates.value.filter(item => item.view_type === viewType),
  ]),
) as Record<DetailViewType, CharacterViewImageTemplate[]>)

const refresh = async () => {
  const [configResponse, templateResponse] = await Promise.all([
    api.get('/api/character-generation/configs'),
    api.get('/api/character-generation/configs/templates'),
  ])
  configs.value = configResponse.data
  templates.value = templateResponse.data
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

const beforeTemplateUpload = (file: File) => {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    message.error('仅支持 PNG、JPEG、WebP 图片')
    return false
  }
  uploadFile.value = file
  if (uploadPreview.value) URL.revokeObjectURL(uploadPreview.value)
  uploadPreview.value = URL.createObjectURL(file)
  return false
}

const createTemplate = async () => {
  if (!uploadFile.value || !templateForm.name.trim()) return
  loading.value = true
  try {
    const payload = new FormData()
    payload.append('view_type', templateForm.view_type)
    payload.append('name', templateForm.name.trim())
    payload.append('gender', templateForm.gender)
    payload.append('sort_order', String(templateForm.sort_order))
    payload.append('file', uploadFile.value)
    await api.post('/api/character-generation/configs/templates', payload)
    templateForm.name = ''
    uploadFile.value = null
    if (uploadPreview.value) URL.revokeObjectURL(uploadPreview.value)
    uploadPreview.value = null
    await refresh()
    message.success('身体局部图片模板已添加，测试 Web 用户现在可以下拉选择')
  } finally {
    loading.value = false
  }
}

const saveTemplate = async (template: CharacterViewImageTemplate) => {
  loading.value = true
  try {
    const response = await api.patch(`/api/character-generation/configs/templates/${template.id}`, {
      name: template.name,
      gender: template.gender,
      sort_order: template.sort_order,
      status: template.status,
    })
    templates.value = templates.value.map(item => item.id === template.id ? response.data : item)
    message.success('图片模板设置已保存')
  } finally {
    loading.value = false
  }
}

onMounted(() => void refresh())
</script>

<template>
  <section>
    <a-tabs v-model:active-key="section">
      <a-tab-pane key="prompts" tab="基础视图生成配置">
        <a-alert
          class="mb-4"
          type="info"
          show-icon
          message="这里只配置正脸、裸体正面全身、穿衣正面全身三个可生成视图。身体局部视图使用下方图片模板库，不生成提示词。"
        />
        <a-tabs v-model:active-key="active" tab-position="left">
          <a-tab-pane v-for="config in configs" :key="config.view_type" :tab="config.display_name" />
        </a-tabs>

        <a-form v-if="activeConfig" layout="vertical" class="mt-4 max-w-5xl">
          <div class="mb-3 flex flex-wrap items-center gap-2 text-xs">
            <a-tag :color="activeConfig.config_source === 'database' ? 'green' : 'blue'">
              {{ activeConfig.config_source === 'database' ? '数据库配置' : '内置默认' }}
            </a-tag>
            <span class="opacity-60">{{ activeConfig.view_type }} · revision {{ activeConfig.revision }}</span>
          </div>
          <a-form-item label="子图展示名称"><a-input v-model:value="activeConfig.display_name" /></a-form-item>
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
      </a-tab-pane>

      <a-tab-pane key="templates" tab="身体局部图片模板">
        <a-alert class="mb-4" type="info" show-icon message="每个局部槽位可以配置多张图片模板。启用的模板会出现在测试 Web 人物工作台下拉列表，用户仍可上传自己的图片替换。" />
        <div class="mb-6 grid gap-4 rounded-xl border p-4 md:grid-cols-[180px_1fr]">
          <a-upload :show-upload-list="false" :before-upload="beforeTemplateUpload" accept="image/png,image/jpeg,image/webp">
            <div class="flex h-44 cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-dashed bg-slate-50">
              <img v-if="uploadPreview" :src="uploadPreview" class="h-full w-full object-contain" />
              <span v-else class="text-xs text-slate-500">选择模板图片</span>
            </div>
          </a-upload>
          <a-form layout="vertical" class="grid gap-x-3 md:grid-cols-2">
            <a-form-item label="局部槽位"><a-select v-model:value="templateForm.view_type"><a-select-option v-for="(label, key) in viewLabels" :key="key" :value="key">{{ label }}</a-select-option></a-select></a-form-item>
            <a-form-item label="模板名称"><a-input v-model:value="templateForm.name" :maxlength="80" /></a-form-item>
            <a-form-item label="适用性别"><a-select v-model:value="templateForm.gender"><a-select-option v-for="(label, key) in genderLabels" :key="key" :value="key">{{ label }}</a-select-option></a-select></a-form-item>
            <a-form-item label="排序"><a-input-number v-model:value="templateForm.sort_order" class="w-full" /></a-form-item>
            <div class="md:col-span-2 text-right"><a-button type="primary" :disabled="!uploadFile || !templateForm.name.trim()" :loading="loading" @click="createTemplate">添加图片模板</a-button></div>
          </a-form>
        </div>

        <div v-for="(label, viewType) in viewLabels" :key="viewType" class="mb-7">
          <h3 class="mb-3 text-base font-semibold">{{ label }}</h3>
          <a-empty v-if="groupedTemplates[viewType].length === 0" description="暂无模板" />
          <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <article v-for="template in groupedTemplates[viewType]" :key="template.id" class="rounded-xl border p-3">
              <img :src="template.preview_url" class="mb-3 h-48 w-full rounded-lg bg-slate-100 object-contain" />
              <div class="space-y-2">
                <a-input v-model:value="template.name" :maxlength="80" />
                <div class="grid grid-cols-3 gap-2">
                  <a-select v-model:value="template.gender"><a-select-option v-for="(genderLabel, key) in genderLabels" :key="key" :value="key">{{ genderLabel }}</a-select-option></a-select>
                  <a-input-number v-model:value="template.sort_order" class="w-full" />
                  <a-select v-model:value="template.status"><a-select-option value="active">启用</a-select-option><a-select-option value="disabled">停用</a-select-option></a-select>
                </div>
                <a-button block :loading="loading" @click="saveTemplate(template)">保存模板设置</a-button>
              </div>
            </article>
          </div>
        </div>
      </a-tab-pane>
    </a-tabs>
  </section>
</template>
