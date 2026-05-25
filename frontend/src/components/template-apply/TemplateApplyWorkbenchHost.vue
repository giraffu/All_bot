<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useTemplateApplyCloseProtocol } from '@/composables/useTemplateApplyCloseProtocol'
import { useI18n } from 'vue-i18n'
import { useViewport } from '@/composables/useViewport'
import {
  useMainLayoutContentRef,
  useWorkbenchScrollLock
} from '@/composables/useWorkbenchScrollLock'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { CloseTrigger } from '@/types/templateApply'

const TemplateImagePromptPanel = defineAsyncComponent(
  () => import('@/components/template-apply/TemplateImagePromptPanel.vue')
)
const TemplateImageToVideoPanel = defineAsyncComponent(
  () => import('@/components/template-apply/TemplateImageToVideoPanel.vue')
)
const TemplateFaceSwapPanel = defineAsyncComponent(
  () => import('@/components/template-apply/TemplateFaceSwapPanel.vue')
)
const TemplateVideoSwapPanel = defineAsyncComponent(
  () => import('@/components/template-apply/TemplateVideoSwapPanel.vue')
)

const templateApplyStore = useTemplateApplyStore()
const { t } = useI18n()
const { isMobile } = useViewport()
const { attemptTemplateApplyClose } = useTemplateApplyCloseProtocol(templateApplyStore)

const contentRef = useMainLayoutContentRef()
const isWorkbenchVisible = computed(() => templateApplyStore.visible)
const panelTitle = computed(() =>
  templateApplyStore.featureTitleKey ? t(templateApplyStore.featureTitleKey) : t('template_apply.default_title')
)

const resolvedPanel = computed(() => {
  switch (templateApplyStore.panelKind) {
    case 'imagePrompt':
      return TemplateImagePromptPanel
    case 'imageToVideo':
      return TemplateImageToVideoPanel
    case 'faceSwap':
      return TemplateFaceSwapPanel
    case 'videoSwap':
      return TemplateVideoSwapPanel
    default:
      return null
  }
})

const handleCloseAttempt = async (trigger: CloseTrigger) => {
  await attemptTemplateApplyClose(trigger)
}

useWorkbenchScrollLock(contentRef, isWorkbenchVisible)
</script>

<template>
  <a-drawer
    v-if="isMobile"
    :open="templateApplyStore.visible"
    :title="panelTitle"
    width="100%"
    placement="right"
    :mask-closable="false"
    :keyboard="false"
    :destroy-on-close="true"
    @close="handleCloseAttempt('gesture_close')"
  >
    <component
      :is="resolvedPanel"
      v-if="resolvedPanel && templateApplyStore.session && templateApplyStore.context"
      :key="templateApplyStore.session.sessionId"
      :session-id="templateApplyStore.session.sessionId"
      :context="templateApplyStore.context"
    />
  </a-drawer>

  <a-modal
    v-else
    :open="templateApplyStore.visible"
    :title="panelTitle"
    :footer="null"
    :mask-closable="false"
    :keyboard="false"
    :destroy-on-close="true"
    :width="1200"
    centered
    wrap-class-name="template-apply-workbench-modal"
    @cancel="handleCloseAttempt('user_close')"
  >
    <component
      :is="resolvedPanel"
      v-if="resolvedPanel && templateApplyStore.session && templateApplyStore.context"
      :key="templateApplyStore.session.sessionId"
      :session-id="templateApplyStore.session.sessionId"
      :context="templateApplyStore.context"
    />
  </a-modal>
</template>

<style scoped>
:deep(.template-apply-workbench-modal .ant-modal-body) {
  padding-top: 12px;
}
</style>
