<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  getFleet,
  initializeSecurity,
  refreshFleet,
  switchProfile,
} from './api'
import type { Candidate, Fleet, Operation, PhysicalSlot } from './types'

const fleet = ref<Fleet | null>(null)
const loading = ref(true)
const message = ref('')
const operation = ref<Operation | null>(null)
const selected = ref<{ card: PhysicalSlot; candidate: Candidate } | null>(null)
const confirmation = ref('')
let eventSource: EventSource | null = null

const grouped = computed(() => {
  const groups = new Map<string, PhysicalSlot[]>()
  for (const card of fleet.value?.physical_slots ?? []) {
    const rows = groups.get(card.node_id) ?? []
    rows.push(card)
    groups.set(card.node_id, rows)
  }
  return [...groups.entries()]
})

const switchBlocked = computed(
  () =>
    !fleet.value ||
    fleet.value.state.status !== 'passed' ||
    fleet.value.state.stale ||
    Boolean(fleet.value.active_operation || operation.value),
)

const terminal = new Set([
  'succeeded',
  'failed',
  'rolled_back',
  'interrupted',
  'recovery_required',
])

function formatTime(value?: string | null) {
  if (!value) return '尚未采集'
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(new Date(value))
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
  }
  return code ? labels[code] ?? code : ''
}

async function loadFleet() {
  try {
    fleet.value = await getFleet()
    message.value = ''
  } catch (error) {
    message.value = error instanceof Error ? error.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function watchOperation(value: Operation) {
  operation.value = value
  eventSource?.close()
  eventSource = new EventSource(
    `/api/v1/operations/${encodeURIComponent(value.operation_id)}/events`,
  )
  eventSource.onmessage = async (event) => {
    const next = JSON.parse(event.data) as Operation
    operation.value = next
    if (terminal.has(next.status)) {
      eventSource?.close()
      await loadFleet()
      window.setTimeout(() => {
        operation.value = null
      }, 5000)
    }
  }
  eventSource.onerror = () => eventSource?.close()
}

async function refresh() {
  try {
    watchOperation(await refreshFleet())
  } catch (error) {
    message.value = error instanceof Error ? error.message : '刷新失败'
  }
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
        <h1>LAN AIO 资源管理</h1>
        <p class="subtitle">查看每张物理显卡的当前运行类型，并执行受控单卡切换。</p>
      </div>
      <button class="refresh" :disabled="Boolean(operation)" @click="refresh">
        <span>↻</span> 刷新实时状态
      </button>
    </header>

    <section v-if="fleet" class="status-strip" :class="fleet.state.status">
      <div>
        <span class="status-dot"></span>
        <strong>{{ fleet.state.status === 'passed' ? '状态一致，可执行切换' : '只读保护已启用' }}</strong>
        <span>Live {{ formatTime(fleet.state.captured_at) }}</span>
      </div>
      <span v-if="fleet.state.stale" class="pill warning">状态已过期</span>
      <span v-if="fleet.state.drift.length" class="pill danger">
        {{ fleet.state.drift.length }} 项漂移
      </span>
    </section>

    <section v-if="operation" class="operation-panel">
      <div>
        <p class="eyebrow">ACTIVE OPERATION</p>
        <strong>{{ operation.kind === 'refresh' ? '全量实时巡检' : '单卡类型切换' }}</strong>
      </div>
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
    <div v-if="loading" class="empty">正在读取 catalog 与本地账本…</div>

    <section v-for="[node, cards] in grouped" :key="node" class="node-section">
      <div class="node-heading">
        <div>
          <p class="eyebrow">GPU NODE</p>
          <h2>{{ node }}</h2>
        </div>
        <span>{{ cards.length }} 张物理卡</span>
      </div>

      <div class="card-grid">
        <article v-for="card in cards" :key="card.physical_slot" class="gpu-card">
          <div class="card-head">
            <div class="gpu-index">GPU {{ card.gpu_index }}</div>
            <span class="port">:{{ card.host_port }}</span>
            <span
              class="runtime-state"
              :class="card.current ? 'running' : 'empty-state'"
            >
              {{ card.current ? card.worker?.status ?? 'last-known' : '空置' }}
            </span>
          </div>

          <div class="current-profile">
            <span>当前类型</span>
            <strong>{{ card.current?.profile ?? 'intentionally_empty' }}</strong>
            <small v-if="card.worker?.current_task_type">
              任务：{{ card.worker.current_task_type }}
            </small>
            <small v-else-if="card.intentionally_empty?.reason">
              {{ card.intentionally_empty.reason }}
            </small>
            <small v-else>当前无执行中任务</small>
          </div>

          <div class="candidate-title">
            <span>可选 LAN AIO 类型</span>
            <span>{{ card.candidates.length }}</span>
          </div>
          <div class="candidates">
            <button
              v-for="candidate in card.candidates"
              :key="candidate.slot_id"
              class="candidate"
              :class="{
                current: candidate.slot_id === card.current?.slot_id,
                blocked: !candidate.switchable && candidate.slot_id !== card.current?.slot_id,
              }"
              :disabled="switchBlocked || !candidate.switchable"
              :title="candidate.notes ?? ''"
              @click="openSwitch(card, candidate)"
            >
              <span>
                <strong>{{ candidate.profile }}</strong>
                <small>{{ candidate.phase }}</small>
              </span>
              <i :class="cacheClass(candidate)">
                {{ candidate.cache?.cache_state ?? 'cache unknown' }}
              </i>
            </button>
          </div>

          <div v-if="card.blocked_observations.length" class="observations">
            <strong>风险记录</strong>
            <p v-for="item in card.blocked_observations" :key="item.profile">
              {{ item.profile }} · {{ item.reason }}
            </p>
          </div>
          <footer>Ledger {{ formatTime(card.last_verified_at) }}</footer>
        </article>
      </div>
    </section>

    <div v-if="selected" class="modal-backdrop" @click.self="selected = null">
      <section class="modal">
        <p class="eyebrow">PRODUCTION SWITCH</p>
        <h2>确认单卡类型切换</h2>
        <div class="switch-route">
          <span>{{ selected.card.current?.profile ?? '空置' }}</span>
          <b>→</b>
          <strong>{{ selected.candidate.profile }}</strong>
        </div>
        <p>
          目标为 {{ selected.card.physical_slot }}。系统会重新巡检、等待任务自然空闲，并在失败时自动回滚。
        </p>
        <label>
          输入目标类型 <code>{{ selected.candidate.profile }}</code>
          <input v-model="confirmation" autocomplete="off" />
        </label>
        <div class="modal-actions">
          <button class="ghost" @click="selected = null">取消</button>
          <button
            class="danger-button"
            :disabled="confirmation !== selected.candidate.profile"
            @click="confirmSwitch"
          >
            执行切换
          </button>
        </div>
      </section>
    </div>
  </main>
</template>
