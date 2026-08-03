<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api/client'

type Asset = { id: string; name: string; description: string; status: string; preview_url?: string; category?: string; moderation_status?: string; views?: Array<{ type: string; status: string; prompt: string; preview_url?: string }> }
const active = ref('characters')
const characters = ref<Asset[]>([])
const environments = ref<Asset[]>([])
const privateCharacters = ref<Asset[]>([])
const loading = ref(false)
const form = reactive({ name: '', description: '', category: '' })

const refresh = async () => {
  loading.value = true
  try {
    const [characterResponse, environmentResponse, privateResponse] = await Promise.all([
      api.get('/api/reference-assets/characters'), api.get('/api/reference-assets/environments'), api.get('/api/reference-assets/private-characters'),
    ])
    characters.value = characterResponse.data
    environments.value = environmentResponse.data
    privateCharacters.value = privateResponse.data
  } finally { loading.value = false }
}
const create = async () => {
  const path = active.value === 'characters' ? 'characters' : 'environments'
  await api.post(`/api/reference-assets/${path}`, { ...form, tags: [], sort_order: 0 })
  form.name = ''; form.description = ''; form.category = ''; await refresh()
}
const upload = async (asset: Asset, file: File, kind: 'source' | 'environment' | string) => {
  const body = new FormData(); body.append('file', file)
  const path = kind === 'environment'
    ? `/api/reference-assets/environments/${asset.id}/upload`
    : kind === 'source'
      ? `/api/reference-assets/characters/${asset.id}/source/upload`
      : `/api/reference-assets/characters/${asset.id}/views/${kind}/upload`
  await api.post(path, body); await refresh(); return false
}
const compose = async (asset: Asset) => { await api.post(`/api/reference-assets/characters/${asset.id}/compose`); await refresh() }
const setStatus = async (asset: Asset, status: string) => {
  const path = active.value === 'characters' ? 'characters' : 'environments'
  await api.patch(`/api/reference-assets/${path}/${asset.id}`, { status }); await refresh()
}
const generateView = async (asset: Asset, view: NonNullable<Asset['views']>[number]) => {
  await api.post(`/api/reference-assets/characters/${asset.id}/views/${view.type}/generate`, { prompt: view.prompt, engine: 'free_edit_v3' })
  await refresh()
}
const generateEnvironment = async (asset: Asset) => {
  await api.post(`/api/reference-assets/environments/${asset.id}/generate`, { prompt: asset.description || asset.name })
  await refresh()
}
const moderate = async (asset: Asset, disabled: boolean) => {
  await api.put(`/api/reference-assets/private-characters/${asset.id}/moderation`, { disabled, reason: disabled ? '管理员停用' : '' })
  await refresh()
}
onMounted(() => void refresh())
</script>

<template>
  <section class="space-y-4">
    <a-tabs v-model:active-key="active"><a-tab-pane key="characters" tab="官方角色图库"/><a-tab-pane key="environments" tab="官方环境图库"/><a-tab-pane key="private" tab="用户私有角色"/></a-tabs>
    <a-card v-if="active !== 'private'" title="新建素材">
      <div class="grid gap-3 md:grid-cols-3"><a-input v-model:value="form.name" placeholder="名称"/><a-input v-model:value="form.description" placeholder="描述"/><a-input v-if="active === 'environments'" v-model:value="form.category" placeholder="分类"/></div>
      <a-button class="mt-3" type="primary" :disabled="!form.name.trim()" @click="create">新建</a-button>
    </a-card>
    <a-spin :spinning="loading">
      <div class="grid gap-4 xl:grid-cols-2">
        <a-card v-for="asset in active === 'characters' ? characters : active === 'environments' ? environments : privateCharacters" :key="asset.id" :title="asset.name">
          <template #extra><a-tag>{{ asset.status }}</a-tag></template>
          <img v-if="asset.preview_url" :src="asset.preview_url" class="mb-3 max-h-48 rounded object-contain"/>
          <p>{{ asset.description }}</p>
          <template v-if="active === 'characters'">
            <a-upload :show-upload-list="false" :before-upload="(file: File) => upload(asset, file, 'source')"><a-button>上传角色源图</a-button></a-upload>
            <div class="mt-3 grid grid-cols-2 gap-2">
              <div v-for="view in asset.views" :key="view.type" class="rounded border p-2 text-xs">
                <img v-if="view.preview_url" :src="view.preview_url" class="mb-2 h-24 w-full object-contain"/>
                <div>{{ view.type }} · {{ view.status }}</div>
                <a-upload :show-upload-list="false" :before-upload="(file: File) => upload(asset, file, view.type)"><a-button size="small">上传视图</a-button></a-upload>
                <a-button size="small" class="ml-1" :disabled="!view.prompt" @click="generateView(asset, view)">免扣费生成</a-button>
              </div>
            </div>
            <a-button class="mt-3" @click="compose(asset)">合成 1536×896 面板</a-button>
          </template>
          <template v-else-if="active === 'environments'">
            <a-upload :show-upload-list="false" :before-upload="(file: File) => upload(asset, file, 'environment')"><a-button>上传环境图</a-button></a-upload>
            <a-button class="ml-2" @click="generateEnvironment(asset)">免扣费生成</a-button>
          </template>
          <div v-if="active !== 'private'" class="mt-3 flex gap-2"><a-button @click="setStatus(asset, 'published')">发布</a-button><a-button danger @click="setStatus(asset, 'archived')">软归档</a-button></div>
          <div v-else class="mt-3"><a-tag>{{ asset.moderation_status }}</a-tag><a-button v-if="asset.moderation_status !== 'disabled'" danger @click="moderate(asset, true)">停用</a-button><a-button v-else @click="moderate(asset, false)">恢复</a-button></div>
        </a-card>
      </div>
    </a-spin>
  </section>
</template>
