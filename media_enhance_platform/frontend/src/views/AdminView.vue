<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { CircleDollarSign, RotateCcw, Shield, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'
import type { Task, Ticket, User } from '@/types'

const { t } = useI18n()
const tab = ref<'tasks' | 'users' | 'tickets'>('tasks')
const tasks = ref<Task[]>([])
const users = ref<User[]>([])
const tickets = ref<Ticket[]>([])
const summary = ref<Record<string, any>>({})
const reason = ref('Customer support adjustment')
const adjustment = ref(10)

async function load() {
  ;[tasks.value, users.value, tickets.value, summary.value] = await Promise.all([
    api<Task[]>('/admin/tasks'), api<User[]>('/admin/users'), api<Ticket[]>('/admin/tickets'), api<Record<string, any>>('/admin/summary'),
  ])
}
async function retry(task: Task) {
  await api(`/admin/tasks/${task.id}/retry`, { method: 'POST' }); await load()
}
async function refund(task: Task) {
  const points = Number(prompt(t('admin.refund'), String(task.charged_points - task.refunded_points)))
  if (!points) return
  await api(`/admin/tasks/${task.id}/refund`, { method: 'POST', body: JSON.stringify({ points, reason: reason.value, idempotency_key: `ui-refund-${task.id}-${Date.now()}` }) }); await load()
}
async function adjust(user: User) {
  await api('/admin/points/adjust', { method: 'POST', body: JSON.stringify({ user_id: user.id, points: adjustment.value, reason: reason.value, idempotency_key: `ui-adjust-${user.id}-${Date.now()}` }) }); await load()
}
async function updateTicket(ticket: Ticket) {
  const reply = prompt(t('admin.reply'), ticket.admin_reply || '') ?? ''
  await api(`/admin/tickets/${ticket.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'resolved', admin_reply: reply }) }); await load()
}
async function deleteFile(fileId: string) {
  if (!confirm(t('common.delete'))) return
  await api(`/admin/files/${fileId}`, { method: 'DELETE' }); await load()
}
onMounted(load)
</script>

<template>
  <section class="app-page admin-page">
    <div class="app-heading"><div><span class="section-index">OPERATIONS</span><h1>{{ t('admin.title') }}</h1></div><div class="admin-stat"><Shield :size="20" /><b>{{ summary.users || 0 }}</b><span>Users</span></div></div>
    <div class="admin-tabs">
      <button :class="{ active: tab === 'tasks' }" @click="tab = 'tasks'">{{ t('admin.tasks') }}</button>
      <button :class="{ active: tab === 'users' }" @click="tab = 'users'">{{ t('admin.users') }}</button>
      <button :class="{ active: tab === 'tickets' }" @click="tab = 'tickets'">{{ t('admin.tickets') }}</button>
    </div>
    <div v-if="tab === 'tasks'" class="admin-table">
      <article v-for="task in tasks" :key="task.id">
        <div><small>{{ task.id }}</small><b>{{ t(`workspace.types.${task.task_type}`) }} · {{ task.multiplier }}×</b></div>
        <span class="status-pill" :class="task.status">{{ t(`workspace.status.${task.status}`) }}</span>
        <span>{{ task.cost_points }} {{ t('common.points') }}</span>
        <div class="row-actions">
          <button v-if="task.status === 'failed'" class="icon-button" @click="retry(task)"><RotateCcw :size="16" />{{ t('common.retry') }}</button>
          <button v-if="task.status === 'succeeded' && task.refunded_points < task.charged_points" class="icon-button" @click="refund(task)"><CircleDollarSign :size="16" />{{ t('admin.refund') }}</button>
          <button class="icon-button danger" @click="deleteFile(task.output_file_id || task.source_file_id)"><Trash2 :size="16" /></button>
        </div>
      </article>
    </div>
    <div v-if="tab === 'users'" class="admin-table">
      <div class="admin-controls"><input v-model.number="adjustment" type="number" /><input v-model="reason" /><span>{{ t('admin.reason') }}</span></div>
      <article v-for="user in users" :key="user.id">
        <div><small>{{ user.role }}</small><b>{{ user.email }}</b></div><span>{{ user.available_points }} + {{ user.reserved_points }}</span>
        <button class="glass-button" @click="adjust(user)">{{ t('admin.adjust') }}</button>
      </article>
    </div>
    <div v-if="tab === 'tickets'" class="admin-table">
      <article v-for="ticket in tickets" :key="ticket.id">
        <div><small>{{ ticket.kind }} · {{ ticket.email }}</small><b>{{ ticket.subject }}</b><p>{{ ticket.content }}</p></div>
        <span class="status-pill" :class="ticket.status">{{ ticket.status }}</span>
        <button class="glass-button" @click="updateTicket(ticket)">{{ t('admin.reply') }}</button>
      </article>
    </div>
  </section>
</template>
