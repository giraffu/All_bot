<script setup lang="ts">
import { computed } from 'vue'

interface ChannelMetric {
  amount: number
  orders: number
}

type ChannelKey = 'direct_alipay' | 'collected_alipay' | 'collected_wechat'

const props = withDefaults(defineProps<{
  total?: number
  channels?: Partial<Record<ChannelKey | 'legacy_unclassified', ChannelMetric>>
}>(), {
  total: 0,
  channels: () => ({}),
})

const emptyMetric = (): ChannelMetric => ({ amount: 0, orders: 0 })
const channelMeta: Array<{ key: ChannelKey, label: string, hint: string, tone: string }> = [
  { key: 'direct_alipay', label: '支付宝直连', hint: '官方直连结算', tone: 'direct' },
  { key: 'collected_alipay', label: '代收 · 支付宝', hint: '第三方代收通道', tone: 'alipay' },
  { key: 'collected_wechat', label: '代收 · 微信', hint: '第三方代收通道', tone: 'wechat' },
]

const cards = computed(() => channelMeta.map(meta => {
  const metric = props.channels[meta.key] ?? emptyMetric()
  return {
    ...meta,
    ...metric,
    share: props.total > 0 ? metric.amount / props.total * 100 : 0,
  }
}))
const legacy = computed(() => props.channels.legacy_unclassified ?? emptyMetric())
const currency = (value: number) => `¥${Number(value || 0).toLocaleString('zh-CN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})}`
</script>

<template>
  <section class="rmb-breakdown" aria-labelledby="rmb-breakdown-title">
    <header class="rmb-breakdown__header">
      <div>
        <p class="rmb-breakdown__eyebrow">RMB 渠道构成</p>
        <h2 id="rmb-breakdown-title">三类充值渠道</h2>
      </div>
      <div class="rmb-breakdown__total">
        <span>累计收入</span>
        <strong>{{ currency(total) }}</strong>
      </div>
    </header>

    <div class="rmb-breakdown__grid">
      <article
        v-for="card in cards"
        :key="card.key"
        data-testid="rmb-channel-card"
        class="rmb-channel-card"
        :class="`rmb-channel-card--${card.tone}`"
      >
        <div class="rmb-channel-card__topline">
          <span class="rmb-channel-card__dot" aria-hidden="true" />
          <div>
            <h3>{{ card.label }}</h3>
            <p>{{ card.hint }}</p>
          </div>
        </div>
        <strong class="rmb-channel-card__amount">{{ currency(card.amount) }}</strong>
        <div class="rmb-channel-card__meta">
          <span>{{ card.orders }} 笔成功订单</span>
          <span>{{ card.share.toFixed(1) }}%</span>
        </div>
        <div class="rmb-channel-card__track" aria-hidden="true">
          <span :style="{ width: `${Math.min(card.share, 100)}%` }" />
        </div>
      </article>
    </div>

    <p v-if="legacy.amount || legacy.orders" class="rmb-breakdown__legacy">
      历史未区分 {{ currency(legacy.amount) }} · {{ legacy.orders }} 笔
      <span>（旧订单未保存代收支付方式，未强行归类）</span>
    </p>
  </section>
</template>

<style scoped>
.rmb-breakdown { padding: 22px; border: 1px solid #e8edf5; border-radius: 16px; background: linear-gradient(135deg, #fff 0%, #f8fbff 100%); box-shadow: 0 8px 30px rgba(15, 23, 42, .05); }
.rmb-breakdown__header { display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.rmb-breakdown__eyebrow { margin: 0 0 3px; color: #64748b; font-size: 12px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
h2, h3, p { margin-top: 0; }
h2 { margin-bottom: 0; color: #0f172a; font-size: 20px; }
.rmb-breakdown__total { text-align: right; }
.rmb-breakdown__total span { display: block; color: #64748b; font-size: 12px; }
.rmb-breakdown__total strong { color: #e11d48; font-size: 25px; letter-spacing: -.02em; }
.rmb-breakdown__grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.rmb-channel-card { --tone: #1677ff; --soft: #eff6ff; padding: 17px; border: 1px solid color-mix(in srgb, var(--tone) 23%, white); border-radius: 14px; background: linear-gradient(145deg, #fff 30%, var(--soft)); }
.rmb-channel-card--alipay { --tone: #f59e0b; --soft: #fffbeb; }
.rmb-channel-card--wechat { --tone: #16a34a; --soft: #f0fdf4; }
.rmb-channel-card__topline { display: flex; align-items: flex-start; gap: 10px; }
.rmb-channel-card__dot { width: 9px; height: 9px; margin-top: 5px; border-radius: 999px; background: var(--tone); box-shadow: 0 0 0 5px color-mix(in srgb, var(--tone) 12%, transparent); }
.rmb-channel-card h3 { margin-bottom: 2px; color: #1e293b; font-size: 14px; }
.rmb-channel-card p { margin-bottom: 0; color: #94a3b8; font-size: 12px; }
.rmb-channel-card__amount { display: block; margin: 17px 0 11px; color: #0f172a; font-size: 24px; }
.rmb-channel-card__meta { display: flex; justify-content: space-between; color: #64748b; font-size: 12px; }
.rmb-channel-card__track { height: 4px; margin-top: 9px; overflow: hidden; border-radius: 999px; background: #e2e8f0; }
.rmb-channel-card__track span { display: block; height: 100%; border-radius: inherit; background: var(--tone); }
.rmb-breakdown__legacy { margin: 14px 0 0; padding-top: 13px; border-top: 1px dashed #dbe3ef; color: #64748b; font-size: 12px; }
.rmb-breakdown__legacy span { color: #94a3b8; }
@media (max-width: 900px) { .rmb-breakdown__grid { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .rmb-breakdown { padding: 16px; } .rmb-breakdown__header { align-items: flex-start; flex-direction: column; } .rmb-breakdown__total { text-align: left; } }
</style>
