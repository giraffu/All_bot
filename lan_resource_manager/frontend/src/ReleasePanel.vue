<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  alignWorkspaces,
  buildModules,
  deployModules,
  getModuleCatalog,
  getOperation,
  integrateWorkspaces,
  scanWorkspaces,
} from './api'
import type {
  ModuleCatalog,
  Operation,
  WorkspaceScan,
} from './types'

const emit = defineEmits<{
  operation: [value: Operation | null]
}>()

const scan = ref<WorkspaceScan | null>(null)
const catalog = ref<ModuleCatalog | null>(null)
const selectedSlots = ref<string[]>([])
const selectedModules = ref<string[]>([])
const environment = ref<'test' | 'prod'>('test')
const artifacts = ref<Record<string, string>>({})
const targets = ref<Record<string, { operator: 'runpod' | 'lan'; slot: string }>>({})
const workspaceConfirmation = ref('')
const buildConfirmation = ref('')
const deployConfirmation = ref('')
const busy = ref(false)
const message = ref('')

const pendingBySlot = computed(() => {
  const grouped = new Map<string, number>()
  for (const row of scan.value?.queue.pending ?? []) {
    if (row.slot) grouped.set(row.slot, (grouped.get(row.slot) ?? 0) + 1)
  }
  return grouped
})
const sortedSlots = computed(() => [...selectedSlots.value].sort())
const sortedModules = computed(() => [...selectedModules.value].sort())
const integrationPhrase = computed(
  () => `INTEGRATE ${sortedSlots.value.join(',')} ${scan.value?.main_sha ?? ''}`,
)
const alignmentPhrase = computed(
  () => `ALIGN ${sortedSlots.value.join(',')} ${scan.value?.main_sha ?? ''}`,
)
const buildPhrase = computed(
  () => `BUILD ${sortedModules.value.join(',')} ${scan.value?.main_sha ?? ''}`,
)
const deployPhrase = computed(
  () => `DEPLOY ${environment.value.toUpperCase()} ${sortedModules.value.join(',')}`,
)
const modules = computed(() =>
  Object.entries(catalog.value?.modules ?? {})
    .filter(([, info]) =>
      !info.build_only && info.environments.includes(environment.value),
    )
    .sort(([left], [right]) => left.localeCompare(right)),
)
const selectedArtifacts = computed(() =>
  Object.fromEntries(
    sortedModules.value
      .filter((name) => artifacts.value[name])
      .map((name) => [name, artifacts.value[name]]),
  ),
)
const canIntegrate = computed(
  () => sortedSlots.value.length > 0
    && sortedSlots.value.every((slot) => pendingBySlot.value.has(slot)),
)
const canDeploy = computed(
  () => sortedModules.value.length > 0
    && Object.keys(selectedArtifacts.value).length === sortedModules.value.length
    && (environment.value === 'prod' || sortedModules.value.length <= 2)
    && sortedModules.value.every((name) => {
      const info = catalog.value?.modules[name]
      return !info?.requires_target
        || Boolean(targets.value[name]?.slot && targets.value[name]?.operator)
    }),
)

function shortSha(value?: string | null) {
  return value ? `${value.slice(0, 10)}…` : '未读取'
}

async function load() {
  message.value = ''
  try {
    ;[scan.value, catalog.value] = await Promise.all([
      scanWorkspaces(),
      getModuleCatalog(),
    ])
    selectedSlots.value = selectedSlots.value.filter((slot) =>
      scan.value?.slots.some((row) => row.slot === slot),
    )
  } catch (error) {
    message.value = error instanceof Error ? error.message : '扫描失败'
  }
}

function toggleModule(name: string) {
  if (selectedModules.value.includes(name)) {
    selectedModules.value = selectedModules.value.filter((item) => item !== name)
    return
  }
  if (environment.value === 'test' && selectedModules.value.length >= 2) {
    message.value = '测试环境每次最多选择两个模块'
    return
  }
  const info = catalog.value?.modules[name]
  if (info?.requires_target && selectedModules.value.length) {
    message.value = 'GPU 模块必须单独选择并指定精确槽位'
    return
  }
  if (selectedModules.value.some(
    (item) => catalog.value?.modules[item]?.requires_target,
  )) {
    message.value = 'GPU 模块必须单独选择并指定精确槽位'
    return
  }
  if (info?.requires_target && !targets.value[name]) {
    targets.value[name] = { operator: 'lan', slot: '' }
  }
  selectedModules.value = [...selectedModules.value, name]
}

async function track(operation: Operation) {
  busy.value = true
  emit('operation', operation)
  try {
    let current = operation
    while (!['succeeded', 'failed', 'interrupted', 'recovery_required'].includes(current.status)) {
      await new Promise((resolve) => window.setTimeout(resolve, 400))
      current = await getOperation(operation.operation_id)
      emit('operation', current)
    }
    if (current.status !== 'succeeded') {
      throw new Error(current.error_code || `${current.kind} failed`)
    }
    return current
  } finally {
    busy.value = false
    emit('operation', null)
  }
}

async function runWorkspace(action: 'integrate' | 'align') {
  if (!scan.value) return
  try {
    const phrase = action === 'integrate'
      ? integrationPhrase.value
      : alignmentPhrase.value
    const operation = action === 'integrate'
      ? await integrateWorkspaces(
          scan.value.main_sha,
          sortedSlots.value,
          workspaceConfirmation.value,
        )
      : await alignWorkspaces(
          scan.value.main_sha,
          sortedSlots.value,
          workspaceConfirmation.value,
        )
    await track(operation)
    workspaceConfirmation.value = ''
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '槽位操作失败'
  }
}

async function runBuild() {
  if (!scan.value) return
  try {
    const completed = await track(await buildModules(
      scan.value.main_sha,
      sortedModules.value,
      buildConfirmation.value,
    ))
    const result = completed.result as { artifacts?: Record<string, string> } | null
    artifacts.value = { ...artifacts.value, ...(result?.artifacts ?? {}) }
    buildConfirmation.value = ''
    message.value = '所选模块产物已构建并记录精确 digest'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '模块构建失败'
  }
}

async function runDeploy() {
  try {
    await track(await deployModules(
      environment.value,
      selectedArtifacts.value,
      targets.value,
      deployConfirmation.value,
    ))
    deployConfirmation.value = ''
    message.value = `${environment.value} 所选模块部署完成`
  } catch (error) {
    message.value = error instanceof Error ? error.message : '模块部署失败'
  }
}

function changeEnvironment(next: 'test' | 'prod') {
  environment.value = next
  selectedModules.value = []
  deployConfirmation.value = ''
  message.value = ''
}

onMounted(load)
</script>

<template>
  <section class="deploy-heading">
    <div>
      <p class="eyebrow">MODULE RELEASE CONTROL</p>
      <h2>模块构建部署</h2>
      <p class="muted">人工选择槽位与模块；平台只调用现有协调器和精确产物发布器。</p>
    </div>
    <button class="refresh" :disabled="busy" @click="load">↻ 扫描槽位与模块</button>
  </section>

  <p v-if="message" class="notice">{{ message }}</p>

  <section class="deploy-card integration-card">
    <div class="form-title">
      <div><p class="eyebrow">A–H WORKSPACES</p><h3>开发槽扫描与协调</h3></div>
      <span>main {{ shortSha(scan?.main_sha) }}</span>
    </div>
    <div class="integration-summary">
      <div><strong>{{ scan?.queue.pending.length ?? 0 }}</strong><span>pending</span></div>
      <div><strong>{{ scan?.queue.integrating.length ?? 0 }}</strong><span>integrating</span></div>
      <div><strong>{{ scan?.queue['needs-rebase'].length ?? 0 }}</strong><span>needs-rebase</span></div>
      <div><strong>{{ selectedSlots.length }}</strong><span>已选择槽位</span></div>
    </div>
    <div class="workspace-grid">
      <label
        v-for="row in scan?.slots ?? []"
        :key="row.slot"
        class="workspace-option"
        :class="{ selected: selectedSlots.includes(row.slot), dirty: !row.clean }"
      >
        <input v-model="selectedSlots" type="checkbox" :value="row.slot" :disabled="busy" />
        <strong>{{ row.slot }}</strong>
        <span>{{ pendingBySlot.has(row.slot) ? `${pendingBySlot.get(row.slot)} 个 pending handoff` : row.branch ? row.branch : row.at_base ? '已对齐 main' : '可安全对齐' }}</span>
        <small>{{ row.clean ? shortSha(row.head) : '脏工作区，不会改动' }}</small>
      </label>
    </div>
    <p class="muted">合入只处理所选槽位对应的 pending handoff；冲突单独进入 needs-rebase。对齐只刷新所选且 clean、已合入的槽位。</p>
    <div class="confirm-stack">
      <label>确认短语
        <input v-model="workspaceConfirmation" :placeholder="canIntegrate ? integrationPhrase : alignmentPhrase" />
      </label>
      <div class="integration-actions">
        <button
          data-action="integrate-selected"
          class="primary"
          :disabled="busy || !canIntegrate || workspaceConfirmation !== integrationPhrase"
          @click="runWorkspace('integrate')"
        >合入所选 handoff</button>
        <button
          data-action="align-selected"
          class="primary"
          :disabled="busy || !selectedSlots.length || workspaceConfirmation !== alignmentPhrase"
          @click="runWorkspace('align')"
        >对齐所选槽位</button>
      </div>
    </div>
  </section>

  <section class="deploy-card module-release-card">
    <div class="form-title">
      <div><p class="eyebrow">EXPLICIT MODULES</p><h3>选择模块、构建、部署</h3></div>
      <div class="environment-switch">
        <button :class="{ active: environment === 'test' }" @click="changeEnvironment('test')">测试环境</button>
        <button :class="{ active: environment === 'prod' }" @click="changeEnvironment('prod')">正式环境</button>
      </div>
    </div>
    <p v-if="environment === 'test'" class="muted">测试环境每次选择 1–2 个模块；未配置 test 目标的模块不会出现。</p>
    <p v-else class="muted">正式环境可在管理后台多选模块；执行仍逐模块记录结果，并要求正式确认短语。</p>
    <div class="module-grid">
      <button
        v-for="[name, info] in modules"
        :key="name"
        class="module-option"
        :class="{ selected: selectedModules.includes(name) }"
        :disabled="busy"
        @click="toggleModule(name)"
      >
        <span><strong>{{ name }}</strong><small>{{ info.adapter }}</small></span>
        <i>{{ artifacts[name] ? 'digest ready' : '待构建' }}</i>
      </button>
    </div>
    <div
      v-for="name in selectedModules.filter((item) => catalog?.modules[item]?.requires_target)"
      :key="`target-${name}`"
      class="gpu-target"
    >
      <strong>{{ name }} 精确 GPU 目标</strong>
      <select v-model="targets[name].operator">
        <option value="lan">LAN</option>
        <option value="runpod">RunPod</option>
      </select>
      <input v-model="targets[name].slot" placeholder="exact-slot" />
    </div>
    <div class="release-actions">
      <div class="confirm-stack">
        <label>构建确认 <code>{{ buildPhrase }}</code>
          <input v-model="buildConfirmation" />
        </label>
        <button
          data-action="build-selected"
          class="primary"
          :disabled="busy || !selectedModules.length || buildConfirmation !== buildPhrase"
          @click="runBuild"
        >构建所选模块</button>
      </div>
      <div class="confirm-stack">
        <label>部署确认 <code>{{ deployPhrase }}</code>
          <input v-model="deployConfirmation" />
        </label>
        <button
          data-action="deploy-selected"
          class="danger-button"
          :disabled="busy || !canDeploy || deployConfirmation !== deployPhrase"
          @click="runDeploy"
        >部署所选模块到{{ environment === 'test' ? '测试' : '正式' }}环境</button>
      </div>
    </div>
    <div v-if="Object.keys(selectedArtifacts).length" class="artifact-list">
      <div v-for="(artifact, name) in selectedArtifacts" :key="name">
        <strong>{{ name }}</strong><code>{{ artifact }}</code>
      </div>
    </div>
  </section>
</template>
