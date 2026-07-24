<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { fetchSupportTicket, fetchSupportTickets, replySupportTicket, updateSupportTicket } from '../api/api'
import { formatSupportTicketCategory, SUPPORT_TICKET_CATEGORY_OPTIONS } from '../supportTicketCategories'

type Ticket = { id: number; category: string; status: string; username?: string; full_name?: string; last_message_at: string }
type TicketDetail = Ticket & { telegram_user_id: number; messages: Array<{ id: number; sender_type: string; body?: string; attachments: Array<{ filename: string; mime_type?: string; url: string }>; created_at: string }> }
const tickets = ref<Ticket[]>([])
const selected = ref<TicketDetail | null>(null)
const status = ref<string | undefined>()
const category = ref<string | undefined>()
const reply = ref('')
const internalNote = ref('')
const loading = ref(false)
const labelSender: Record<string, string> = { user: '用户', admin: '管理员', internal: '内部备注' }
const isImage = (mimeType?: string) => Boolean(mimeType?.startsWith('image/'))
const load = async () => { loading.value = true; try { tickets.value = (await fetchSupportTickets({ status: status.value ?? null, category: category.value ?? null })).items } finally { loading.value = false } }
const openTicket = async (id: number) => { selected.value = await fetchSupportTicket(id) }
const updateStatus = async () => { if (!selected.value) return; await updateSupportTicket(selected.value.id, { status: selected.value.status, internal_note: internalNote.value || null }); internalNote.value = ''; await openTicket(selected.value.id); await load() }
const sendReply = async () => { if (!selected.value || !reply.value.trim()) return; await replySupportTicket(selected.value.id, { body: reply.value, status: selected.value.status }); reply.value = ''; await openTicket(selected.value.id); await load() }
const detailTitle = computed(() => selected.value ? `工单 #${selected.value.id}` : '选择一条工单')
onMounted(load)
</script>

<template>
  <div class="support-grid">
    <section class="ticket-list ticket-scroll-pane" aria-label="工单列表" tabindex="0">
      <div class="toolbar"><a-select v-model:value="status" class="status-filter" allow-clear placeholder="状态" :options="['open','processing','resolved','closed'].map(value => ({ value, label: value }))" @change="load" /><a-select v-model:value="category" class="category-filter" allow-clear placeholder="分类" :options="SUPPORT_TICKET_CATEGORY_OPTIONS" @change="load" /><a-button @click="load">刷新</a-button></div>
      <a-spin :spinning="loading"><a-list :data-source="tickets" bordered><template #renderItem="{ item }"><a-list-item class="ticket-item" @click="openTicket(item.id)"><div><strong>#{{ item.id }} {{ formatSupportTicketCategory(item.category) }}</strong><div>{{ item.full_name || item.username || item.id }}</div><small>{{ item.last_message_at }}</small></div><a-tag :color="item.status === 'open' ? 'red' : 'blue'">{{ item.status }}</a-tag></a-list-item></template></a-list></a-spin>
    </section>
    <section class="ticket-detail ticket-scroll-pane" aria-label="工单详情" tabindex="0"><h2>{{ detailTitle }}</h2><template v-if="selected"><div class="meta">用户：{{ selected.full_name || selected.username || selected.telegram_user_id }} · {{ formatSupportTicketCategory(selected.category) }}</div><div class="messages"><article v-for="message in selected.messages" :key="message.id" :class="`message ${message.sender_type}`"><b>{{ labelSender[message.sender_type] }}</b><p v-if="message.body">{{ message.body }}</p><a v-for="attachment in message.attachments" :key="attachment.url" class="attachment" :href="attachment.url" target="_blank" rel="noreferrer"><img v-if="isImage(attachment.mime_type)" class="attachment-image" :src="attachment.url" :alt="attachment.filename" /><span>{{ attachment.filename }}</span></a><small>{{ message.created_at }}</small></article></div><a-select v-model:value="selected.status" :options="['open','processing','resolved','closed'].map(value => ({value,label:value}))" /><a-textarea v-model:value="internalNote" placeholder="内部备注（用户不可见）" :rows="2" /><a-button @click="updateStatus">保存状态/备注</a-button><a-textarea v-model:value="reply" placeholder="回复用户" :rows="3" /><a-button type="primary" @click="sendReply">发送回复</a-button></template></section>
  </div>
</template>

<style scoped>
.support-grid { display:grid; grid-template-columns: minmax(280px, 35%) 1fr; gap:16px; min-height:0; flex:1; overflow:hidden }
.ticket-scroll-pane { min-height:0; overflow-x:hidden; overflow-y:scroll; scrollbar-gutter:stable; scrollbar-width:auto; scrollbar-color:#94a3b8 #f1f5f9 }
.ticket-scroll-pane::-webkit-scrollbar { width:12px }
.ticket-scroll-pane::-webkit-scrollbar-track { background:#f1f5f9; border-radius:10px }
.ticket-scroll-pane::-webkit-scrollbar-thumb { background:#94a3b8; border:2px solid #f1f5f9; border-radius:10px }
.ticket-scroll-pane::-webkit-scrollbar-thumb:hover { background:#64748b }
.ticket-scroll-pane:focus-visible { outline:2px solid #1677ff; outline-offset:2px }
.toolbar { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px }.status-filter { width:110px }.category-filter { width:140px }.ticket-item { cursor:pointer }.messages { margin:16px 0 }.message { padding:10px; margin:8px 0; border-radius:8px; background:#f5f5f5 }.message.admin { background:#e6f4ff }.message.internal { background:#fffbe6 }.message p { white-space:pre-wrap; margin:6px 0 }.message a,.message small { display:block }.attachment { width:max-content; max-width:100%; margin:8px 0 }.attachment-image { display:block; max-width:min(360px, 100%); max-height:280px; border-radius:8px; object-fit:contain; margin-bottom:4px }.ticket-detail :deep(.ant-input),.ticket-detail :deep(.ant-select),.ticket-detail :deep(.ant-btn) { margin:6px 0; width:100% } @media (max-width: 800px) { .support-grid { grid-template-columns:1fr; grid-template-rows:repeat(2, minmax(0, 1fr)) } }
</style>
