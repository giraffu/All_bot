<script setup lang="ts">
import { Clock, Globe, Wallet } from 'lucide-vue-next'

defineProps<{
  fullName?: string | null
  username?: string | null
  userGroupLabel: string
  identityLabel: string
  identityExpireText: string
  credits: number
  localeValue: string
  checkinLoading: boolean
  onToggleLanguage: () => void
  onCheckin: () => void
}>()
</script>

<template>
  <div class="welcome-banner bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-500 rounded-xl p-5 md:p-8 text-white shadow-lg relative overflow-hidden border border-indigo-400/50">
    <div class="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center">
      <div class="w-full md:w-auto">
        <h1 class="text-xl md:text-3xl font-bold mb-3 md:mb-2 drop-shadow-sm text-slate-100">
          {{ $t('profile.welcome_back', { name: fullName || username }) }}
        </h1>

        <div class="flex flex-wrap items-center gap-2 mb-3 md:mb-2 text-sm md:text-lg text-slate-300">
          <div class="flex items-center bg-white/5 backdrop-blur-sm border border-white/10 rounded px-2.5 py-1">
            <span class="mr-1.5 text-slate-400">{{ $t('profile.group') }}:</span>
            <span class="font-bold text-cyan-300 drop-shadow-sm">{{ userGroupLabel }}</span>
          </div>
          <div class="flex items-center bg-white/5 backdrop-blur-sm border border-white/10 rounded px-2.5 py-1">
            <span class="mr-1.5 text-slate-400">{{ $t('profile.identity') }}:</span>
            <span class="font-bold text-cyan-300 drop-shadow-sm">{{ identityLabel }}</span>
          </div>
          <button
            class="flex items-center bg-cyan-500/10 hover:bg-cyan-500/20 backdrop-blur-sm border border-cyan-500/30 hover:border-cyan-500/50 rounded px-2.5 py-1 cursor-pointer transition-all"
            @click="onToggleLanguage"
          >
            <Globe :size="16" class="mr-1.5 text-cyan-400" />
            <span class="font-bold text-cyan-300 drop-shadow-sm text-sm">
              {{ localeValue === 'zh' ? 'English' : '中文' }}
            </span>
          </button>
        </div>

        <div class="text-xs md:text-sm text-slate-400 flex items-center drop-shadow-sm">
          <Clock :size="14" class="mr-1.5 text-slate-500" />
          <span>{{ identityExpireText }}</span>
        </div>
      </div>

      <div class="mt-5 md:mt-0 w-full md:w-auto flex flex-col items-end gap-3 border-t border-white/20 md:border-0 pt-4 md:pt-0">
        <div class="flex items-center bg-white/20 backdrop-blur-md px-4 py-2 md:px-5 md:py-3 rounded-lg border border-white/30 shadow-inner w-full md:w-auto justify-between md:justify-start">
          <div class="flex items-center">
            <Wallet :size="20" class="mr-2 md:mr-3 text-cyan-200 drop-shadow-[0_0_8px_rgba(255,255,255,0.5)]" />
            <div class="flex flex-col">
              <span class="text-[10px] md:text-xs text-slate-400 font-medium leading-none mb-1">{{ $t('profile.credits') }}</span>
              <span class="text-lg md:text-2xl font-bold leading-none drop-shadow-sm text-slate-100">{{ credits }}</span>
            </div>
          </div>
        </div>
        <a-button
          type="primary"
          :loading="checkinLoading"
          class="bg-gradient-to-r from-indigo-500 to-cyan-600 hover:from-indigo-400 hover:to-cyan-500 border-none text-white font-bold px-6 w-full shadow-lg hover:shadow-cyan-500/20 transition-all transform hover:-translate-y-0.5 h-10 md:h-auto z-50 pointer-events-auto"
          @click="onCheckin"
        >
          {{ $t('profile.checkin_btn') }}
        </a-button>
      </div>
    </div>

    <div class="absolute -top-24 -right-24 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute -bottom-24 right-12 w-48 h-48 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none"></div>
  </div>
</template>
