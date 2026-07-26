<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  createDeploymentPlan,
  executeDeploymentPlan,
  getDeploymentCatalog,
  getEnvironmentStatus,
  getFleet,
  getReleaseCandidate,
  initializeSecurity,
  refreshFleet,
  setMaintenance,
  startTrustedBuild,
  switchProfile,
} from './api'
import type {
  Candidate,
  DeploymentCatalog,
  DeploymentPlan,
  EnvironmentStatus,
  Fleet,
  Operation,
  PhysicalSlot,
  ReleaseCandidate,
} from './types'

const tab = ref<'lan' | 'deploy'>('lan')
const fleet = ref<Fleet | null>(null)
const loading = ref(true)
const message = ref('')
const operation = ref<Operation | null>(null)
const selected = ref<{ card: PhysicalSlot; candidate: Candidate } | null>(null)
const confirmation = ref('')
const catalog = ref<DeploymentCatalog | null>(null)
const releaseCandidate = ref<ReleaseCandidate | null>(null)
const environment = ref<'test' | 'prod'>('test')
const environmentStatus = ref<EnvironmentStatus | null>(null)
const moduleName = ref('')
const maintenanceMode = ref<'planner' | 'rolling'>('planner')
const plan = ref<DeploymentPlan | null>(null)
const deployConfirmation = ref('')
const buildConfirmation = ref('')
const maintenanceReason = ref('')
const maintenanceConfirmation = ref('')
let eventSource: EventSource | null = null

const terminal = new Set([
  'succeeded', 'failed', 'rolled_back', 'interrupted', 'recovery_required',
])
const grouped = computed(() => {
  const groups = new Map<string, PhysicalSlot[]>()
  for (const card of fleet.value?.physical_slots ?? []) {
    const rows = groups.get(card.node_id) ?? []
    rows.push(card)
    groups.set(card.node_id, rows)
  }
  return [...groups.entries()]
})
const availableModules = computed(
  () => catalog.value?.environments[environment.value]?.modules ?? [],
)
const switchBlocked = computed(
  () => !fleet.value || fleet.value.state.status !== 'passed' ||
    fleet.value.state.stale || Boolean(fleet.value.active_operation || operation.value),
)
const buildPhrase = computed(
  () => `BUILD ${releaseCandidate.value?.main_sha ?? ''}`,
)
const deployPhrase = computed(() => {
  if (!plan.value) return ''
  return `${plan.value.environment.toUpperCase()} ${plan.value.module} ${plan.value.candidate_sha}`
})
const maintenancePhrase = computed(() => {
  const state = environmentStatus.value?.maintenance.enabled ? 'OFF' : 'ON'
  return `${environment.value.toUpperCase()} MAINTENANCE ${state}`
})

function formatTime(value?: string | null) {
  if (!value) return '尚未采集'
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'short', timeStyle: 'medium',
  }).format(new Date(value))
}
function shortSha(value?: string | null) {
  return value ? `${value.slice(0, 10)}…` : '无'
}
function cacheClass(candidate: Candidate) {
  return candidate.cache?.cache_state === 'ready' ? 'ready' : 'warning'
}
function errorLabel(code?: string | null) {
  const labels: Record<string, string> = {
    fleet_state_blocked: '三方状态不一致，切换已阻断',
    current_slot_changed: '当前类型已变化，请刷新后重试',
    switch_rolled_back: '切换失败，已自动回滚',
    recovery_required: '自动恢复失败，需要宿主 CLI 介入',
    operator_switch_failed: 'Operator 切换失败',
    deployment_failed: '部署失败，请查看远端事务状态',
    trusted_build_dispatch_failed: '可信构建触发失败',
    maintenance_update_failed: '维护状态更新失败',
  }
  return code ? labels[code] ?? code : ''
}
async function loadFleet() {
  try {
    fleet.value = await getFleet()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '加载失败'
  } finally {
    loading.value = false
  }
}
async function loadDeployment() {
  const results = await Promise.allSettled([
    getDeploymentCatalog(),
    getReleaseCandidate(),
    getEnvironmentStatus(environment.value),
  ])
  if (results[0].status === 'fulfilled') catalog.value = results[0].value
  if (results[1].status === 'fulfilled') releaseCandidate.value = results[1].value
  if (results[2].status === 'fulfilled') {
    environmentStatus.value = results[2].value
  } else {
    environmentStatus.value = null
  }
  if (!availableModules.value.includes(moduleName.value)) {
    moduleName.value = availableModules.value[0] ?? ''
  }
  const errors = results
    .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
    .map((result) => result.reason instanceof Error ? result.reason.message : '部署状态读取失败')
  message.value = errors.join(' · ')
}
function watchOperation(value: Operation) {
  operation.value = value
  eventSource?.close()
  eventSource = new EventSource(`/api/v1/operations/${encodeURIComponent(value.operation_id)}/events`)
  eventSource.onmessage = async (event) => {
    const next = JSON.parse(event.data) as Operation
    operation.value = next
    if (terminal.has(next.status)) {
      eventSource?.close()
      await Promise.all([loadFleet(), tab.value === 'deploy' ? loadDeployment() : Promise.resolve()])
      window.setTimeout(() => { operation.value = null }, 5000)
    }
  }
  eventSource.onerror = () => eventSource?.close()
}
async function refresh() {
  try { watchOperation(await refreshFleet()) }
  catch (error) { message.value = error instanceof Error ? error.message : '刷新失败' }
}
function openSwitch(card: PhysicalSlot, candidate: Candidate) {
  selected.value = { card, candidate }
  confirmation.value = ''
}
async function confirmSwitch() {
  if (!selected.value) return
  const { card, candidate } = selected.value
  try {
    const next = await switchProfile(card.node_id, card.gpu_index, {
      target_slot_id: candidate.slot_id,
      expected_current_slot_id: card.current?.slot_id ?? null,
      confirmation_profile: confirmation.value,
    })
    selected.value = null
    watchOperation(next)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '提交失败'
  }
}
async function triggerBuild() {
  if (!releaseCandidate.value) return
  try {
    watchOperation(await startTrustedBuild({
      expected_main_sha: releaseCandidate.value.main_sha,
      confirmation: buildConfirmation.value,
    }))
    buildConfirmation.value = ''
  } catch (error) {
    message.value = error instanceof Error ? error.message : '构建触发失败'
  }
}
async function generatePlan() {
  if (!releaseCandidate.value?.deployable_sha || !moduleName.value) return
  try {
    plan.value = await createDeploymentPlan({
      environment: environment.value,
      module: moduleName.value,
      candidate_sha: releaseCandidate.value.deployable_sha,
      maintenance: maintenanceMode.value,
    })
    deployConfirmation.value = ''
  } catch (error) {
    message.value = error instanceof Error ? error.message : '计划生成失败'
  }
}
async function executePlan() {
  if (!plan.value) return
  try {
    watchOperation(await executeDeploymentPlan(plan.value.plan_id, deployConfirmation.value))
    plan.value = null
    deployConfirmation.value = ''
  } catch (error) {
    message.value = error instanceof Error ? error.message : '部署提交失败'
  }
}
async function changeMaintenance() {
  if (!environmentStatus.value) return
  const enabled = !environmentStatus.value.maintenance.enabled
  try {
    watchOperation(await setMaintenance(environment.value, {
      enabled,
      expected_enabled: !enabled,
      reason: maintenanceReason.value,
      confirmation: maintenanceConfirmation.value,
    }))
    maintenanceReason.value = ''
    maintenanceConfirmation.value = ''
  } catch (error) {
    message.value = error instanceof Error ? error.message : '维护状态提交失败'
  }
}
async function selectTab(next: 'lan' | 'deploy') {
  tab.value = next
  if (next === 'deploy' && !catalog.value) await loadDeployment()
}
watch(environment, async () => {
  plan.value = null
  maintenanceMode.value = 'planner'
  if (tab.value === 'deploy') await loadDeployment()
})
onMounted(async () => {
  try {
    await initializeSecurity()
    await loadFleet()
    if (fleet.value?.active_operation) watchOperation(fleet.value.active_operation)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '初始化失败'
    loading.value = false
  }
})
onBeforeUnmount(() => eventSource?.close())
</script>

<template>
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">ALLBOT · LOCAL CONTROL PLANE</p>
        <h1>本地资源管理平台</h1>
        <p class="subtitle">受控管理 LAN AIO 映射、可信构建与模块化部署。</p>
      </div>
      <button v-if="tab === 'lan'" class="refresh" :disabled="Boolean(operation)" @click="refresh">
        <span>↻</span> 刷新实时状态
      </button>
      <button v-else class="refresh" :disabled="Boolean(operation)" @click="loadDeployment">
        <span>↻</span> 刷新部署状态
      </button>
    </header>

    <nav class="tabs" aria-label="资源管理分类">
      <button data-tab="lan" :class="{ active: tab === 'lan' }" @click="selectTab('lan')">LAN AIO 资源管理</button>
      <button data-tab="deploy" :class="{ active: tab === 'deploy' }" @click="selectTab('deploy')">模块构建部署</button>
    </nav>

    <section class="lan-warning">
      <strong>局域网匿名管理</strong>
      <span>同网段设备可访问；所有写操作均要求完整确认短语并记录来源 IP。</span>
    </section>

    <section v-if="operation" class="operation-panel">
      <div><p class="eyebrow">ACTIVE OPERATION</p><strong>{{ operation.kind }}</strong></div>
      <div class="operation-progress">
        <span class="spinner" :class="{ stopped: terminal.has(operation.status) }"></span>
        <div>
          <strong>{{ operation.stage }}</strong>
          <p>{{ operation.status }} · {{ operation.operation_id }}</p>
          <p v-if="operation.error_code" class="error">{{ errorLabel(operation.error_code) }}</p>
        </div>
      </div>
    </section>
    <p v-if="message" class="notice error">{{ message }}</p>

    <template v-if="tab === 'lan'">
      <section v-if="fleet" class="status-strip" :class="fleet.state.status">
        <div>
          <span class="status-dot"></span>
          <strong>{{ fleet.state.status === 'passed' ? '状态一致，可执行切换' : '只读保护已启用' }}</strong>
          <span>Live {{ formatTime(fleet.state.captured_at) }}</span>
        </div>
        <span v-if="fleet.state.stale" class="pill warning">状态已过期</span>
        <span v-if="fleet.state.drift.length" class="pill danger">{{ fleet.state.drift.length }} 项漂移</span>
      </section>
      <div v-if="loading" class="empty">正在读取 catalog 与本地账本…</div>
      <section v-for="[node, cards] in grouped" :key="node" class="node-section">
        <div class="node-heading">
          <div><p class="eyebrow">GPU NODE</p><h2>{{ node }}</h2></div>
          <span>{{ cards.length }} 张物理卡</span>
        </div>
        <div class="card-grid">
          <article v-for="card in cards" :key="card.physical_slot" class="gpu-card">
            <div class="card-head">
              <div class="gpu-index">GPU {{ card.gpu_index }}</div>
              <span class="port">:{{ card.host_port }}</span>
              <span class="runtime-state" :class="card.current ? 'running' : 'empty-state'">
                {{ card.current ? card.worker?.status ?? 'last-known' : '空置' }}
              </span>
            </div>
            <div class="current-profile">
              <span>当前类型</span><strong>{{ card.current?.profile ?? 'intentionally_empty' }}</strong>
              <small v-if="card.worker?.current_task_type">任务：{{ card.worker.current_task_type }}</small>
              <small v-else-if="card.intentionally_empty?.reason">{{ card.intentionally_empty.reason }}</small>
              <small v-else>当前无执行中任务</small>
            </div>
            <div class="candidate-title"><span>可选 LAN AIO 类型</span><span>{{ card.candidates.length }}</span></div>
            <div class="candidates">
              <button v-for="candidate in card.candidates" :key="candidate.slot_id" class="candidate"
                :class="{ current: candidate.slot_id === card.current?.slot_id, blocked: !candidate.switchable && candidate.slot_id !== card.current?.slot_id }"
                :disabled="switchBlocked || !candidate.switchable" :title="candidate.notes ?? ''"
                @click="openSwitch(card, candidate)">
                <span><strong>{{ candidate.profile }}</strong><small>{{ candidate.phase }}</small></span>
                <i :class="cacheClass(candidate)">{{ candidate.cache?.cache_state ?? 'cache unknown' }}</i>
              </button>
            </div>
            <div v-if="card.blocked_observations.length" class="observations">
              <strong>风险记录</strong>
              <p v-for="item in card.blocked_observations" :key="item.profile">{{ item.profile }} · {{ item.reason }}</p>
            </div>
            <footer>Ledger {{ formatTime(card.last_verified_at) }}</footer>
          </article>
        </div>
      </section>
    </template>

    <template v-else>
      <section class="deploy-heading">
        <div><p class="eyebrow">IMMUTABLE RELEASES</p><h2>模块构建部署</h2></div>
        <div class="environment-switch">
          <button :class="{ active: environment === 'test' }" @click="environment = 'test'">测试环境</button>
          <button :class="{ active: environment === 'prod' }" @click="environment = 'prod'">正式环境</button>
        </div>
      </section>

      <div class="deploy-grid">
        <section class="deploy-card candidate-card">
          <p class="eyebrow">LATEST MAIN</p>
          <h3>{{ shortSha(releaseCandidate?.main_sha) }}</h3>
          <code>{{ releaseCandidate?.main_sha ?? '正在读取远端 main…' }}</code>
          <div class="trust-row">
            <span :class="releaseCandidate?.ci?.conclusion === 'success' ? 'ok' : 'warn'">
              CI {{ releaseCandidate?.ci?.conclusion ?? releaseCandidate?.ci?.status ?? 'missing' }}
            </span>
            <span :class="releaseCandidate?.bundle.status === 'ready' ? 'ok' : 'warn'">
              {{ releaseCandidate?.bundle.status === 'ready' ? '可信 bundle 已就绪' : 'bundle 待构建' }}
            </span>
          </div>
          <p v-if="releaseCandidate?.scope === 'lightweight'" class="muted">该 SHA 无运行时变更，不需要新 bundle。</p>
          <p v-if="releaseCandidate?.blockers.length" class="error">
            阻断：{{ releaseCandidate.blockers.join(' · ') }}
          </p>
          <div v-if="releaseCandidate?.bundle.status !== 'ready' && !['lightweight', 'release-tooling'].includes(releaseCandidate?.scope ?? '')" class="confirm-stack">
            <label>输入 <code>{{ buildPhrase }}</code><input v-model="buildConfirmation" /></label>
            <button class="primary" :disabled="buildConfirmation !== buildPhrase || Boolean(operation)" @click="triggerBuild">打包构建最新 main</button>
          </div>
        </section>

        <section class="deploy-card maintenance-card" :class="{ held: environmentStatus?.maintenance.enabled }">
          <p class="eyebrow">GENERATION MAINTENANCE</p>
          <h3>{{ environmentStatus?.maintenance.enabled ? '生成维护中' : '正常接收新任务' }}</h3>
          <p class="muted">只阻止新生成请求，不影响历史记录和结果轮询。</p>
          <p v-if="environmentStatus?.maintenance.owner">Owner · {{ environmentStatus.maintenance.owner }}</p>
          <div class="confirm-stack">
            <label>原因<input v-model="maintenanceReason" placeholder="例如：模块发布窗口" /></label>
            <label>输入 <code>{{ maintenancePhrase }}</code><input v-model="maintenanceConfirmation" /></label>
            <button class="maintenance-action"
              :disabled="maintenanceReason.length < 3 || maintenanceConfirmation !== maintenancePhrase || Boolean(operation) || (environmentStatus?.maintenance.enabled && !environmentStatus?.maintenance.can_disable)"
              @click="changeMaintenance">
              {{ environmentStatus?.maintenance.enabled ? '退出维护' : '进入维护' }}
            </button>
          </div>
        </section>
      </div>

      <section class="deploy-card deployment-form">
        <div class="form-title">
          <div><p class="eyebrow">DEPLOYMENT PLAN</p><h3>生成受控发布计划</h3></div>
          <div class="environment-facts">
            <span>当前 {{ shortSha(environmentStatus?.current_sha) }}</span>
            <span>{{ Object.keys(environmentStatus?.artifacts ?? {}).length }} 个已记录产物</span>
            <span v-if="environmentStatus?.config_drift" class="error">配置漂移</span>
            <span v-if="environmentStatus?.active_transaction" class="error">
              未完成事务 · {{ environmentStatus.active_transaction.status }}
            </span>
          </div>
        </div>
        <div class="form-grid">
          <label>独立模块
            <select v-model="moduleName">
              <option v-for="name in availableModules" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>
          <label>维护策略
            <select v-model="maintenanceMode">
              <option value="planner">由发布器规划（推荐）</option>
              <option v-if="environment === 'prod'" value="rolling">请求无维护滚动发布</option>
            </select>
          </label>
          <label>目标 bundle
            <input :value="releaseCandidate?.deployable_sha ?? ''" readonly />
          </label>
        </div>
        <button data-action="create-plan" class="primary"
          :disabled="!moduleName || !releaseCandidate?.deployable_sha || Boolean(operation)"
          @click="generatePlan">生成只读计划</button>
      </section>

      <section v-if="plan" class="deploy-card plan-preview">
        <div class="form-title">
          <div><p class="eyebrow">PLAN READY</p><h3>{{ plan.environment }} · {{ plan.module }}</h3></div>
          <span>{{ plan.preview.maintenance_required ? '需要维护' : '滚动更新' }}</span>
        </div>
        <div class="artifact-list">
          <div v-for="(artifact, name) in plan.preview.artifacts" :key="name">
            <strong>{{ name }}</strong><code>{{ artifact.digest ?? 'digest in bundle' }}</code>
          </div>
        </div>
        <p v-if="plan.preview.blockers?.length" class="error">{{ plan.preview.blockers.join(' · ') }}</p>
        <div class="confirm-stack">
          <label>输入 <code>{{ deployPhrase }}</code><input v-model="deployConfirmation" /></label>
          <button class="danger-button"
            :disabled="deployConfirmation !== deployPhrase || Boolean(plan.preview.blockers?.length) || Boolean(operation)"
            @click="executePlan">执行精确部署</button>
        </div>
      </section>
    </template>

    <div v-if="selected" class="modal-backdrop" @click.self="selected = null">
      <section class="modal">
        <p class="eyebrow">PRODUCTION SWITCH</p><h2>确认单卡类型切换</h2>
        <div class="switch-route"><span>{{ selected.card.current?.profile ?? '空置' }}</span><b>→</b><strong>{{ selected.candidate.profile }}</strong></div>
        <p>目标为 {{ selected.card.physical_slot }}。系统会重新巡检、等待任务自然空闲，并在失败时自动回滚。</p>
        <label>输入目标类型 <code>{{ selected.candidate.profile }}</code><input v-model="confirmation" autocomplete="off" /></label>
        <div class="modal-actions">
          <button class="ghost" @click="selected = null">取消</button>
          <button class="danger-button" :disabled="confirmation !== selected.candidate.profile" @click="confirmSwitch">执行切换</button>
        </div>
      </section>
    </div>
  </main>
</template>
