<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '@/api'
import { message } from 'ant-design-vue'
import { Image as ImageIcon, Video, Clock, PlayCircle } from 'lucide-vue-next'
import dayjs from 'dayjs'

const data = ref<any[]>([])
const loading = ref(false)
const submittingTasks = ref<Record<string, boolean>>({})

const pagination = ref({
  current: 1,
  pageSize: 8,
  total: 0,
  hideOnSinglePage: true // Hide pagination since we only ever show max 8 items now
})

const previewVisible = ref(false)
const previewVideoUrl = ref('')

const showVideoPreview = (url: string) => {
  previewVideoUrl.value = url
  previewVisible.value = true
}

const handlePreviewClose = () => {
  previewVisible.value = false
  previewVideoUrl.value = ''
}

const columns = [
  {
    title: '任务 ID',
    dataIndex: 'task_id',
    key: 'task_id',
    width: 250,
  },
  {
    title: '类型',
    dataIndex: 'type',
    key: 'type',
    width: 120,
  },
  {
    title: '结果',
    dataIndex: 'output_file',
    key: 'output_file',
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 200,
  },
  {
    title: '操作',
    key: 'action',
    width: 120,
    align: 'center'
  }
]

const submitToGallery = async (record: any) => {
  if (submittingTasks.value[record.task_id]) return
  submittingTasks.value[record.task_id] = true
  
  try {
    const res = await api.post(`/gallery/posts/submit/${record.task_id}`)
    message.success(res.data?.message || '投稿成功！')
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
  } catch (error) {
    console.error('Failed to fetch history:', error)
  } finally {
    loading.value = false
  }
}

const handleTableChange = (pag: any) => {
  fetchHistory(pag.current)
}

const formatDate = (dateStr: string) => {
  return dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss')
}

const getTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    'face_swap': '幻想换脸',
    'face_video': '视频换脸',
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

onMounted(() => {
  fetchHistory()
})
</script>

<template>
  <div class="history-container p-6 rounded-xl">
    <div class="flex justify-between items-center mb-6">
      <h2 class="text-2xl font-bold text-slate-200 drop-shadow-sm">生成记录</h2>
      <a-button class="bg-slate-800 text-cyan-200 border-cyan-500/30 hover:bg-slate-700 hover:text-white hover:border-cyan-400" @click="fetchHistory(1)">刷新</a-button>
    </div>

    <!-- Privacy and Convenience Notice -->
    <div class="mb-6 bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-4 flex items-start">
      <div class="text-indigo-400 mr-3 mt-0.5"><Clock :size="18" /></div>
      <div class="text-slate-300 text-sm leading-relaxed">
        <span class="font-semibold text-indigo-300">温馨提示：</span>为了兼顾您的数据隐私与系统的便利性，系统只会为您保留最近的 <span class="text-cyan-400 font-bold mx-1">8</span> 条生成记录。请及时保存您需要的作品哦。
      </div>
    </div>

    <a-table 
      :columns="columns" 
      :data-source="data" 
      :loading="loading"
      :pagination="pagination"
      @change="handleTableChange"
      row-key="id"
      class="custom-dark-table"
    >
      <template #bodyCell="{ column, record }">
        
        <template v-if="column.key === 'task_id'">
          <span class="font-mono text-slate-400 text-xs bg-black/30 px-2 py-1 rounded border border-white/5">{{ record.task_id || 'N/A' }}</span>
        </template>
        
        <template v-else-if="column.key === 'type'">
          <a-tag :color="record.type === 'face_video' ? 'blue' : (record.type === 'face_swap' ? 'purple' : 'cyan')" class="flex items-center w-max bg-black/30 border-white/10">
            <Video v-if="record.type === 'face_video'" :size="14" class="mr-1" />
            <ImageIcon v-else :size="14" class="mr-1" />
            {{ getTypeLabel(record.type) }}
          </a-tag>
        </template>
        
        <template v-else-if="column.key === 'output_file'">
          <div v-if="record.output_file" class="flex items-center justify-center bg-black/40 rounded-lg p-2 border border-white/10 relative overflow-hidden group w-[100px] h-[100px]">
            <!-- Check if video type based on file extension -->
            <template v-if="isVideoFile(record.output_file)">
              <div class="relative w-full h-full cursor-pointer" @click.stop="showVideoPreview(getFileUrl(record.output_file))">
                <video 
                  :src="getFileUrl(record.output_file)" 
                  class="object-cover w-full h-full rounded-md shadow-sm opacity-80 group-hover:opacity-100 transition-opacity pointer-events-none"
                  preload="metadata"
                ></video>
                <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div class="bg-black/50 rounded-full p-2 group-hover:bg-cyan-500/80 transition-colors">
                    <PlayCircle :size="24" class="text-white opacity-90" />
                  </div>
                </div>
              </div>
            </template>
            <a-image 
              v-else
              :width="80" 
              :height="80"
              :src="getFileUrl(record.output_file)" 
              class="object-cover rounded-md shadow-sm"
              :preview="{ src: getFileUrl(record.output_file) }"
            />
          </div>
          <span v-else class="text-slate-500 italic text-sm">无文件</span>
        </template>
        
        <template v-else-if="column.key === 'created_at'">
          <div class="flex items-center text-slate-400 text-sm">
            <Clock :size="14" class="mr-1 opacity-70" />
            {{ formatDate(record.created_at) }}
          </div>
        </template>

        <template v-else-if="column.key === 'action'">
          <a-button 
            v-if="record.output_file && ['i2i_pro', 'edit', 'custom_video', 'video_lora'].includes(record.type)"
            type="primary" 
            size="small" 
            class="bg-gradient-to-r from-cyan-600 to-indigo-600 border-none shadow-[0_0_10px_rgba(56,189,248,0.3)] hover:scale-105 transition-transform text-xs rounded-md"
            :loading="submittingTasks[record.task_id]"
            @click="submitToGallery(record)"
          >
            <span class="flex items-center gap-1">
              <span v-if="submittingTasks[record.task_id]">投稿中</span>
              <span v-else>✨ 一键投稿</span>
            </span>
          </a-button>
          <span v-else-if="!record.output_file" class="text-slate-600 text-xs">暂无文件</span>
          <span v-else class="text-slate-600 text-xs">暂不支持投稿</span>
        </template>
        
      </template>
    </a-table>

    <!-- Video Preview Modal -->
    <div 
      v-if="previewVisible" 
      class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/90 backdrop-blur-sm transition-opacity"
      @click="handlePreviewClose"
    >
      <div class="relative max-w-4xl w-full mx-4 flex flex-col items-center" @click.stop>
        <div class="w-full flex justify-end mb-2">
          <button 
            class="text-white hover:text-cyan-400 transition-colors bg-transparent border-none text-4xl cursor-pointer p-2"
            @click="handlePreviewClose"
            title="关闭"
          >&times;</button>
        </div>
        <video 
          v-if="previewVideoUrl" 
          :src="previewVideoUrl" 
          controls 
          autoplay 
          class="w-full max-h-[80vh] rounded-lg shadow-2xl bg-black outline-none"
        ></video>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-container {
  min-height: 100%;
}
:deep(.custom-dark-table) {
  background: transparent !important;
}
:deep(.custom-dark-table .ant-table) {
  background: transparent !important;
}
:deep(.custom-dark-table .ant-table-thead > tr > th) {
  background: rgba(15, 23, 42, 0.4) !important;
  color: #e2e8f0 !important;
  border-bottom: 1px solid rgba(56, 189, 248, 0.2) !important;
  font-weight: 600;
}
:deep(.custom-dark-table .ant-table-tbody > tr > td) {
  border-bottom: 1px solid rgba(148, 163, 184, 0.1) !important;
  background: transparent !important;
  transition: background 0.3s;
}
:deep(.custom-dark-table .ant-table-tbody > tr:hover > td) {
  background: rgba(56, 189, 248, 0.05) !important;
}
:deep(.custom-dark-table .ant-empty-description) {
  color: #94a3b8 !important;
  opacity: 0.8;
}
</style>
