<script setup lang="ts">
import { reactive, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import {
  completeAffiliateUsdtRedeem,
  rejectAffiliateUsdtRedeem,
} from '../api/api'

type RedeemRecord = {
  redeem_id: number
  amount_usdt: number
  payout_address?: string | null
  user_name?: string | null
  username?: string | null
  user_telegram_id?: number | null
}

const props = defineProps<{ record: RedeemRecord }>()
const emit = defineEmits<{ completed: [] }>()

const completeOpen = ref(false)
const rejectOpen = ref(false)
const loading = ref(false)
const completeForm = reactive({ payoutTxHash: '', adminNote: '' })
const rejectReason = ref('')
const userLabel =
  props.record.username
    ? `@${props.record.username}`
    : props.record.user_name || String(props.record.user_telegram_id || '-')

const complete = async () => {
  if (!completeForm.payoutTxHash.trim()) {
    message.error('请填写链上交易哈希')
    return
  }
  loading.value = true
  try {
    await completeAffiliateUsdtRedeem(props.record.redeem_id, {
      payout_tx_hash: completeForm.payoutTxHash.trim(),
      admin_note: completeForm.adminNote.trim() || null,
    })
    message.success('已确认打款')
    completeOpen.value = false
    emit('completed')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '确认失败')
  } finally {
    loading.value = false
  }
}

const reject = async () => {
  if (!rejectReason.value.trim()) {
    message.error('请填写拒绝原因')
    return
  }
  loading.value = true
  try {
    await rejectAffiliateUsdtRedeem(props.record.redeem_id, {
      reason: rejectReason.value.trim(),
    })
    message.success('已拒绝并解冻返佣')
    rejectOpen.value = false
    emit('completed')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '拒绝失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <a-space>
    <a-button type="primary" size="small" @click="completeOpen = true">确认已打款</a-button>
    <a-button danger size="small" @click="rejectOpen = true">拒绝</a-button>
  </a-space>

  <a-modal
    v-model:open="completeOpen"
    title="确认 USDT-TON 已打款"
    :confirm-loading="loading"
    @ok="complete"
  >
    <a-alert
      type="warning"
      show-icon
      :message="`申请 #${record.redeem_id} · ${userLabel} · ${Number(record.amount_usdt).toFixed(4)} USDT`"
      :description="record.payout_address || '-'"
      class="mb-4"
    />
    <a-input v-model:value="completeForm.payoutTxHash" placeholder="链上交易哈希（必填）" />
    <a-textarea
      v-model:value="completeForm.adminNote"
      class="mt-3"
      placeholder="管理员备注（可选）"
      :maxlength="500"
    />
  </a-modal>

  <a-modal
    v-model:open="rejectOpen"
    title="拒绝并解冻返佣"
    :confirm-loading="loading"
    ok-text="确认拒绝"
    ok-type="danger"
    @ok="reject"
  >
    <a-alert
      type="warning"
      show-icon
      :message="`申请 #${record.redeem_id} · ${userLabel} · ${Number(record.amount_usdt).toFixed(4)} USDT`"
      :description="record.payout_address || '-'"
      class="mb-4"
    />
    <a-textarea v-model:value="rejectReason" placeholder="拒绝原因（必填）" :maxlength="500" />
  </a-modal>
</template>
