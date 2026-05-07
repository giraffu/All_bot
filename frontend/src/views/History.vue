<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api'
import { message, Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { Image as ImageIcon, Video, Clock, Download, Compass, Star, Trash2, Upload } from 'lucide-vue-next'
import dayjs from 'dayjs'
import { useViewport } from '@/composables/useViewport'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { isMobile } = useViewport()
const data = ref<any[]>([])
const loading = ref(false)
const submittingTasks = ref<Record<string, boolean>>({})

const pagination = ref({
  current: 1,
  pageSize: 8,
  total: 0,
  hideOnSinglePage: true // Hide pagination since we only ever show max 8 items now
})

const detailVisible = ref(false)
const currentRecord = ref<any>(null)

const openDetail = (record: any) => {
  currentRecord.value = record
  detailVisible.value = true
}

const submitToGallery = async (record: any) => {
  if (submittingTasks.value[record.task_id]) return
  submittingTasks.value[record.task_id] = true
  
  try {
    const res = await api.post(`/gallery/posts/submit/${record.task_id}`)
    message.success(res.data?.message || '投稿成功！')
    record.is_public = true
  } catch (error: any) {
    console.error(error)
    if (error.response?.data?.detail) {
      message.error(error.response.data.detail)
    } else {
      message.error('投稿失败，请稍后再试')
    }
  } finally {
    submittingTasks.value[record.task_id] = false
  }
}

const fetchHistory = async (page = 1) => {
  loading.value = true
  try {
    const res = await api.get('/users/history', {
      params: { page, size: pagination.value.pageSize }
    })
    data.value = res.data.items
    pagination.value.total = res.data.total
    pagination.value.current = res.data.page
    
    // Check if we need to auto-open a specific task detail
    if (route.query.task_id) {
      const targetId = route.query.task_id as string
      const targetRecord = data.value.find(item => item.task_id === targetId)
      if (targetRecord) {
        openDetail(targetRecord)
      } else if (page === 1) {
        // If not found on first page, maybe it's still generating or on another page.
        // For now, just show a message.
        message.info('未在近期历史中找到该任务记录')
      }
      // Remove query param so it doesn't reopen on refresh
      router.replace({ query: {} })
    }
  } catch (error) {
    console.error('Failed to fetch history:', error)
  } finally {
    loading.value = false
  }
}

const handleFavorite = async (record: any) => {
  if (record.is_favorited) return
  
  const hide = message.loading('正在收藏...', 0)
  try {
    await api.post(`/users/history/${record.task_id}/favorite`)
    hide()
    message.success('已收藏至修仙笔记')
    record.is_favorited = true
  } catch (error: any) {
    console.error(error)
    hide()
    message.error(error.response?.data?.detail || '收藏失败，请稍后再试')
  }
}

const handleDelete = async (record: any, event?: Event) => {
  if (event) event.stopPropagation()
  
  Modal.confirm({
    title: '确认删除',
    content: '确认删除该记录吗？（若已发布至广场也将同步下架）',
    okText: '确认',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        await api.delete(`/users/history/${record.id}`)
        message.success('删除成功')
        data.value = data.value.filter(item => item.id !== record.id)
        if (detailVisible.value && currentRecord.value?.id === record.id) {
          detailVisible.value = false
        }
      } catch (error: any) {
        console.error(error)
        message.error(error.response?.data?.detail || '删除失败，请稍后再试')
      }
    }
  })
}

const formatDate = (dateStr: string) => {
  return dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss')
}

const getTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    'edit': '自由P图',
    'i2i_pro': '幻想换脸',
    'undress': '快速脱衣',
    'masturbation': '快速自慰',
    'face_swap': '快速换脸',
    'face_swap_step1': '快速换脸',
    'face_swap_step2': '快速换脸',
    'face_video': '视频换脸',
    'face_video_step1': '视频换脸',
    'face_video_step2': '视频换脸',
    'random_faceswap': '随机换脸',
    'penetration_step1': '快速抽插',
    'penetration_step2': '快速抽插',
    'perfect_video_insert': '动图传教士',
    'doggy_style': '动图后入',
    'blowjob': '口交黑人',
    'undress_tongue': '脱衣吐舌',
    'closeup_blowjob': '特写口交',
    'custom_video': '自定义图生视频',
    'video_lora': '图生视频(附加模型)',
    'img2img_lora': '图生图(附加模型)',
    'ltx_video': '高级图生视频',
    'template_contribute': '模板共建',
    'txt2img': '文生图'
  }
  return map[type] || type
}

const getFileUrl = (path: string) => {
  if (!path) return ''
  if (path.startsWith('http')) return path
  
  const storageUrl = import.meta.env.VITE_STORAGE_URL || ''
  // Ensure we don't double slash if storageUrl has a trailing slash
  const base = storageUrl.endsWith('/') ? storageUrl.slice(0, -1) : storageUrl
  
  if (!path.startsWith('bot-data/') && !path.startsWith('comfyui-temp/')) {
    // If the path has no slash, it's a direct filename from ComfyUI worker in comfyui-temp
    if (!path.includes('/')) {
      return `${base}/comfyui-temp/${path}`
    }
    // Otherwise, it's a structured path like 12345/output_images/... from bot-data
    return `${base}/bot-data/${path}`
  }
  return `${base}/${path}`
}

const isVideoFile = (path: string) => {
  if (!path) return false
  const lowerPath = path.toLowerCase()
  return lowerPath.endsWith('.mp4') || 
         lowerPath.endsWith('.mov') || 
         lowerPath.endsWith('.webm') || 
         lowerPath.endsWith('.mkv') ||
         lowerPath.endsWith('.avi')
}

const handleDownload = async (record: any) => {
  if (!record.output_file) return;
  const url = getFileUrl(record.output_file);
  const ext = record.output_file.split('.').pop()?.toLowerCase() || (isVideoFile(record.output_file) ? 'mp4' : 'png');
  const filename = `${record.type}_${dayjs(record.created_at).format('YYYYMMDD_HHmmss')}.${ext}`;
  
  const hide = message.loading('正在准备保存...', 0);
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error('Network response was not ok');
    const blob = await response.blob();
    
    // 补充 mime type 防止部分设备无法识别
    let mimeType = blob.type;
    if (!mimeType || mimeType === 'application/octet-stream') {
      if (ext === 'mp4') mimeType = 'video/mp4';
      else if (ext === 'png') mimeType = 'image/png';
      else if (ext === 'jpg' || ext === 'jpeg') mimeType = 'image/jpeg';
      else if (ext === 'gif') mimeType = 'image/gif';
    }
    
    // 判断是否为移动端
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    
    // 移动端优先尝试 Web Share API 唤起原生分享/保存相册菜单
    if (isMobile && navigator.canShare) {
      const file = new File([blob], filename, { type: mimeType });
      if (navigator.canShare({ files: [file] })) {
        hide();
        try {
          await navigator.share({
            files: [file],
            title: '保存作品'
          });
          return;
        } catch (e: any) {
          if (e.name !== 'AbortError') {
            console.warn('Share API failed, fallback to download:', e);
          } else {
            return; // 用户主动取消分享
          }
        }
      }
    }

    // 桌面端或不支持 Share API 的回退下载方案
    const objectUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(objectUrl);
    hide();
    message.success(isMobile ? '已触发下载，若未保存成功请点击预览图长按保存' : '下载成功');
  } catch (error) {
    console.warn('Fetch download failed, falling back to new tab', error);
    hide();
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    message.info('已在新标签页打开，请长按保存');
  }
}

onMounted(() => {
  fetchHistory()
})

watch(() => route.query.task_id, (newTaskId) => {
  if (newTaskId) {
    const targetRecord = data.value.find(item => item.task_id === newTaskId)
    if (targetRecord) {
      openDetail(targetRecord)
      router.replace({ query: {} })
    } else {
      // If not in current data, fetch again
      fetchHistory()
    }
  }
})
</script>

<template>
  <div class="history-container p-4 sm:p-6 rounded-xl text-slate-200">
    <div class="flex justify-between items-center mb-6">
      <h2 class="text-2xl font-bold drop-shadow-sm">{{ $t('history.title') }}</h2>
      <a-button class="bg-slate-500 text-cyan-200 border-cyan-500/30 hover:bg-slate-500 hover:text-white hover:border-cyan-400" @click="fetchHistory(1)">{{ $t('history.refresh') }}</a-button>
    </div>

    <!-- Privacy and Convenience Notice -->
    <div class="mb-6 bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-4 flex items-start">
      <div class="text-indigo-400 mr-3 mt-0.5"><Clock :size="18" /></div>
      <div class="text-slate-300 text-sm leading-relaxed">
        {{ $t('history.warning', { max: 8 }) }}
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="py-8 text-center">
      <div class="inline-block w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin"></div>
    </div>

    <!-- Empty State -->
    <div v-else-if="data.length === 0" class="py-20 text-center text-slate-500">
      <Compass :size="48" class="mx-auto mb-4 opacity-20" />
      <p>暂无记录</p>
    </div>

    <!-- Cards Grid -->
    <div v-else class="columns-2 md:columns-4 gap-3 sm:gap-6">
      <div
        v-for="record in data"
        :key="record.id"
        class="mb-3 sm:mb-6 break-inside-avoid rounded-2xl overflow-hidden relative group cursor-pointer border border-slate-400/50 bg-slate-800 hover:border-cyan-500/40 transition-all duration-300 shadow-lg hover:shadow-[0_8px_30px_rgba(56,189,248,0.15)] hover:-translate-y-1"
        @click="openDetail(record)"
      >
        <!-- Media -->
        <div class="relative w-full overflow-hidden aspect-auto min-h-[120px] flex items-center justify-center bg-slate-900">
          <!-- Delete Button (Top Left) -->
          <button
            class="absolute top-2 left-2 bg-black/60 hover:bg-red-500/80 backdrop-blur-sm rounded-full p-1.5 shadow-sm border border-white/10 z-20 text-slate-300 hover:text-white transition-colors opacity-0 group-hover:opacity-100"
            @click="handleDelete(record, $event)"
            title="删除"
          >
            <Trash2 :size="14" />
          </button>
          <template v-if="record.output_file">
            <video
              v-if="isVideoFile(record.output_file)"
              :src="getFileUrl(record.output_file) + '#t=0.001'"
              class="w-full h-auto object-cover min-h-[120px]"
              preload="metadata"
              muted
              loop
              playsinline
              @mouseenter="(e) => (e.target as HTMLVideoElement).play().catch(()=>{})"
              @mouseleave="(e) => { const v = e.target as HTMLVideoElement; v.pause(); v.currentTime = 0; }"
            ></video>
            <img
              v-else
              :src="getFileUrl(record.output_file)"
              class="w-full h-auto object-cover min-h-[120px]"
              loading="lazy"
            />
          </template>
          <div v-else class="py-10 text-slate-500 italic text-sm">无文件</div>

          <!-- Video Icon Badge (Top Right) -->
          <div v-if="record.output_file && isVideoFile(record.output_file)" class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm rounded-full p-1.5 shadow-sm border border-white/10 z-10">
            <Video :size="14" class="text-indigo-400" />
          </div>

          <!-- Tags Overlay (Always Visible, Bottom) -->
          <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent p-2.5 pt-8 z-10">
            <div class="flex justify-between items-end">
              <div class="flex flex-col gap-1.5 items-start">
                <span class="text-[11px] px-2 py-0.5 rounded-md backdrop-blur-md flex items-center border border-white/20 shadow-sm"
                      :class="record.type === 'face_video' ? 'bg-blue-500/40 text-blue-100' : (record.type === 'face_swap' ? 'bg-purple-500/40 text-purple-100' : 'bg-cyan-500/40 text-cyan-100')">
                  <Video v-if="record.type === 'face_video'" :size="12" class="mr-1 text-blue-300" />
                  <ImageIcon v-else :size="12" class="mr-1 text-cyan-300" />
                  {{ getTypeLabel(record.type) }}
                </span>
                <span class="text-[10px] px-2 py-0.5 rounded-md backdrop-blur-md border border-white/10 shadow-sm"
                      :class="record.source === 'web' ? 'bg-green-500/40 text-green-100' : 'bg-orange-500/40 text-orange-100'">
                  <span v-if="record.source === 'web'">🌐 {{ $t('history.web_creation') }}</span>
                  <span v-else>🤖 {{ $t('history.bot_creation') }}</span>
                </span>
              </div>
              
              <!-- 投稿状态 -->
              <span v-if="['i2i_pro', 'edit', 'custom_video', 'video_lora', 'img2img_lora', 'ltx_video'].includes(record.type) && record.allow_contribute !== false"
                    class="text-[10px] px-2 py-0.5 rounded-full backdrop-blur-md border border-white/20 shadow-sm whitespace-nowrap ml-1"
                    :class="record.is_public ? 'bg-indigo-500/40 text-indigo-100' : 'bg-slate-500/40 text-slate-200'">
                {{ record.is_public ? '已投稿' : '未投稿' }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <a-modal
      v-model:visible="detailVisible"
      :footer="null"
      :closable="false"
      :width="isMobile ? '100%' : '90%'"
      :style="isMobile ? { top: 0, padding: 0, margin: 0, maxWidth: '100%' } : { maxWidth: '1000px', top: '20px' }"
      :wrapClassName="isMobile ? 'mobile-full-modal' : ''"
      class="history-detail-modal"
      :bodyStyle="isMobile ? { padding: 0, backgroundColor: '#0f172a', height: '100vh', overflowY: 'auto' } : { padding: 0, backgroundColor: 'transparent' }"
      destroyOnClose
    >
      <div v-if="currentRecord" class="flex flex-col lg:flex-row bg-[#0f172a] lg:rounded-2xl overflow-hidden border-none lg:border lg:border-slate-400/50 lg:shadow-2xl min-h-[100vh] lg:min-h-0">
        
        <!-- Mobile Header (Back Button) -->
        <div class="lg:hidden absolute top-0 left-0 right-0 z-50 p-4 flex justify-between items-center bg-gradient-to-b from-black/60 to-transparent pointer-events-none">
          <button @click="detailVisible = false" class="text-white bg-black/40 backdrop-blur-md p-2 rounded-full flex items-center justify-center pointer-events-auto">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
          </button>
        </div>

        <!-- Media Area -->
        <div class="w-full lg:w-2/3 bg-black flex items-center justify-center relative min-h-[60vh] lg:min-h-[300px]">
          <template v-if="currentRecord.output_file">
            <video v-if="isVideoFile(currentRecord.output_file)" :src="getFileUrl(currentRecord.output_file)" class="w-full h-auto lg:max-w-full lg:max-h-[80vh] lg:object-contain object-cover" controls autoplay loop playsinline></video>
            <img v-else :src="getFileUrl(currentRecord.output_file)" class="w-full h-auto lg:max-w-full lg:max-h-[80vh] lg:object-contain object-cover" />
          </template>
          <div v-else class="text-slate-500">无文件</div>
        </div>

        <!-- Info Area -->
        <div class="w-full lg:w-1/3 flex flex-col bg-[#0f172a] lg:bg-slate-500/80 lg:backdrop-blur-xl relative pb-[120px] lg:pb-0">
          <!-- Desktop Close button -->
          <button @click="detailVisible = false" class="hidden lg:block absolute top-4 right-4 text-slate-400 hover:text-white transition-colors z-10">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>

          <div class="p-4 lg:p-6 flex-1 flex flex-col">
            <h3 class="text-lg lg:text-xl font-bold text-slate-100 mb-4 flex items-center mt-0 lg:mt-2">
              <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">作品详情</span>
            </h3>

            <div class="space-y-4 lg:space-y-6 mb-6 lg:mb-8">
              <!-- Labels -->
              <div>
                <div class="text-[10px] lg:text-xs text-slate-400 mb-1.5 lg:mb-2 uppercase tracking-wider">类型标签</div>
                <div class="flex flex-wrap gap-1.5 lg:gap-2">
                  <span class="text-xs px-2 py-0.5 lg:text-sm lg:px-3 lg:py-1 rounded-md border border-white/20 bg-black/40 text-white flex items-center shadow-sm">
                    <Video v-if="currentRecord.type === 'face_video'" :size="isMobile ? 12 : 14" class="mr-1 lg:mr-1.5 text-blue-400" />
                    <ImageIcon v-else :size="isMobile ? 12 : 14" class="mr-1 lg:mr-1.5 text-cyan-400" />
                    {{ getTypeLabel(currentRecord.type) }}
                  </span>
                  <span class="text-xs px-2 py-0.5 lg:text-sm lg:px-3 lg:py-1 rounded-md border border-white/10"
                        :class="currentRecord.source === 'web' ? 'bg-green-500/30 text-green-100' : 'bg-orange-500/30 text-orange-100'">
                    {{ currentRecord.source === 'web' ? '🌐 ' + $t('history.web_creation') : '🤖 ' + $t('history.bot_creation') }}
                  </span>
                </div>
              </div>

              <!-- Time -->
              <div>
                <div class="text-[10px] lg:text-xs text-slate-400 mb-1.5 lg:mb-2 uppercase tracking-wider">创建时间</div>
                <div class="flex items-center text-slate-300 text-xs lg:text-sm bg-black/20 w-fit px-2 py-1 lg:px-3 lg:py-1.5 rounded-lg border border-slate-500/30">
                  <Clock :size="isMobile ? 14 : 16" class="mr-1.5 lg:mr-2 text-cyan-400" />
                  {{ formatDate(currentRecord.created_at) }}
                </div>
              </div>
            </div>

            <!-- Desktop Actions -->
            <div class="hidden lg:flex mt-auto flex-col space-y-3 pt-6">
              <template v-if="currentRecord.output_file">
                <a-button
                  v-if="['i2i_pro', 'edit', 'custom_video', 'video_lora', 'img2img_lora', 'ltx_video'].includes(currentRecord.type) && currentRecord.allow_contribute !== false"
                  type="primary"
                  :disabled="currentRecord.is_public"
                  class="w-full h-12 border-none rounded-xl text-base font-medium flex items-center justify-center"
                  :class="currentRecord.is_public ? 'bg-indigo-500/50 text-indigo-100 cursor-not-allowed' : 'bg-gradient-to-r from-cyan-600 to-indigo-600 shadow-[0_0_15px_rgba(56,189,248,0.3)] hover:scale-[1.02] transition-transform'"
                  :loading="submittingTasks[currentRecord.task_id]"
                  @click="!currentRecord.is_public && submitToGallery(currentRecord)"
                >
                  {{ currentRecord.is_public ? '已投稿' : (submittingTasks[currentRecord.task_id] ? $t('history.submitting') : $t('history.submit')) }}
                </a-button>
                <div v-else class="w-full h-12 bg-slate-600/30 border border-slate-500/30 rounded-xl text-slate-400 flex items-center justify-center text-sm">
                  {{ $t('history.cannot_post') }}
                </div>

                <a-button
                  ghost
                  class="w-full h-12 border-slate-500/50 hover:bg-slate-500/30 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center"
                  :class="currentRecord.is_favorited ? 'text-slate-400 cursor-not-allowed' : 'text-amber-400 hover:text-amber-300 hover:border-amber-400/50'"
                  @click="!currentRecord.is_favorited && handleFavorite(currentRecord)"
                >
                  <span class="flex items-center justify-center">
                    <Star :size="18" class="mr-2" :class="{ 'fill-current': currentRecord.is_favorited }" />
                    {{ currentRecord.is_favorited ? '已收藏' : '收藏' }}
                  </span>
                </a-button>

                <a-button
                  ghost
                  class="w-full h-12 text-cyan-400 border-cyan-500/50 hover:text-cyan-300 hover:border-cyan-400 hover:bg-cyan-500/10 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center"
                  @click="handleDownload(currentRecord)"
                >
                  <span class="flex items-center justify-center">
                    <Download :size="18" class="mr-2" />
                    {{ $t('history.save') }}
                  </span>
                </a-button>

                <a-button
                  ghost
                  class="w-full h-12 text-red-400 border-red-500/50 hover:text-red-300 hover:border-red-400 hover:bg-red-500/10 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center mt-3"
                  @click="handleDelete(currentRecord)"
                >
                  <span class="flex items-center justify-center">
                    <Trash2 :size="18" class="mr-2" />
                    删除
                  </span>
                </a-button>
              </template>
              <div v-else class="text-center text-slate-500 italic py-4 border border-dashed border-slate-600 rounded-xl">暂无文件可操作</div>
            </div>
          </div>
        </div>

        <!-- Mobile Bottom Interaction Bar -->
        <div class="lg:hidden fixed bottom-0 left-0 right-0 bg-[#0f172a]/95 backdrop-blur-lg border-t border-slate-800 px-4 py-2 pb-6 flex items-center justify-between z-50 safe-area-bottom">
          <template v-if="currentRecord.output_file">
            <div class="flex gap-6">
              <button class="flex flex-col items-center justify-center gap-1 transition-colors" :class="currentRecord.is_favorited ? 'text-amber-400' : 'text-slate-400 hover:text-slate-200'" @click="!currentRecord.is_favorited && handleFavorite(currentRecord)">
                <Star :size="20" :class="{ 'fill-current': currentRecord.is_favorited }" />
                <span class="text-[10px]">{{ currentRecord.is_favorited ? '已收藏' : '收藏' }}</span>
              </button>
              <button class="flex flex-col items-center justify-center gap-1 text-slate-400 hover:text-slate-200 transition-colors" @click="handleDownload(currentRecord)">
                <Download :size="20" />
                <span class="text-[10px]">保存</span>
              </button>
              <button class="flex flex-col items-center justify-center gap-1 text-slate-400 hover:text-red-400 transition-colors" @click="handleDelete(currentRecord)">
                <Trash2 :size="20" />
                <span class="text-[10px]">删除</span>
              </button>
            </div>
            
            <button 
              v-if="['i2i_pro', 'edit', 'custom_video', 'video_lora', 'img2img_lora', 'ltx_video'].includes(currentRecord.type) && currentRecord.allow_contribute !== false"
              @click="!currentRecord.is_public && submitToGallery(currentRecord)"
              :disabled="currentRecord.is_public || submittingTasks[currentRecord.task_id]"
              class="px-5 py-2 rounded-full font-medium text-sm transition-all flex items-center justify-center min-w-[100px]"
              :class="currentRecord.is_public ? 'bg-indigo-500/30 text-indigo-200' : 'bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg hover:shadow-cyan-500/25'"
            >
              <div v-if="submittingTasks[currentRecord.task_id]" class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-1.5"></div>
              <Upload v-else-if="!currentRecord.is_public" :size="16" class="mr-1.5" />
              <span>{{ currentRecord.is_public ? '已投稿' : (submittingTasks[currentRecord.task_id] ? '投稿中...' : '一键投稿') }}</span>
            </button>
          </template>
          <div v-else class="w-full text-center text-slate-500 text-sm py-2">暂无文件可操作</div>
        </div>

      </div>
    </a-modal>
  </div>
</template>

<style>
.history-detail-modal .ant-modal-content {
  background-color: transparent !important;
  box-shadow: none !important;
}
.history-detail-modal .ant-modal-mask {
  background-color: rgba(0, 0, 0, 0.85) !important;
  backdrop-filter: blur(8px);
}

/* Mobile full screen modal override */
.mobile-full-modal {
  padding: 0 !important;
  margin: 0 !important;
}
.mobile-full-modal .ant-modal {
  top: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  height: 100vh !important;
  max-width: 100% !important;
}
.mobile-full-modal .ant-modal-content {
  border-radius: 0 !important;
  height: 100vh !important;
  overflow-y: auto !important;
  background-color: #0f172a !important;
}
.mobile-full-modal .ant-modal-body {
  height: 100% !important;
}

/* Safe area support for iOS */
@supports (padding-bottom: env(safe-area-inset-bottom)) {
  .safe-area-bottom {
    padding-bottom: calc(0.75rem + env(safe-area-inset-bottom));
  }
}
</style>

<style scoped>
.history-container {
  min-height: 100%;
}
</style>
