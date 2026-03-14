<script setup>
import { ref, onMounted } from 'vue'
import { fetchTemplateContributions, approveTemplateContribution, deleteTemplateContribution, apiBaseUrl } from '../api/api'
import { CheckOutlined, DeleteOutlined, UserOutlined, ClockCircleOutlined, FileImageOutlined, EyeOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'

const contributions = ref([])
const loading = ref(false)
const previewVisible = ref(false)
const previewUrl = ref('')
const previewType = ref('')

const handlePreview = (item) => {
  previewUrl.value = getFullImageUrl(item.preview_url)
  previewType.value = item.file_type
  previewVisible.value = true
}

const loadContributions = async () => {
  loading.value = true
  try {
    contributions.value = await fetchTemplateContributions()
  } catch (err) {
    console.error('Error fetching contributions:', err)
    message.error('无法加载模板贡献列表')
  } finally {
    loading.value = false
  }
}

const handleApprove = (item) => {
  const rewardAmount = item.file_type === 'video' ? 20 : 10
  Modal.confirm({
    title: '确认采纳该模板？',
    content: `采纳后文件将移动到${item.file_type === 'video' ? ' video_nice ' : ' quick_face '}模板库，并标记为已审核。同时将为用户增加 ${rewardAmount} 灵石奖励。`,
    onOk: async () => {
      try {
        await approveTemplateContribution(item.id)
        message.success(`模板已采纳，并已发放 ${rewardAmount} 灵石奖励`)
        loadContributions()
      } catch (err) {
        message.error('操作失败')
      }
    }
  })
}

const handleDelete = (item) => {
  Modal.confirm({
    title: '确认删除该贡献？',
    content: '删除后文件将从服务器永久移除。',
    okType: 'danger',
    onOk: async () => {
      try {
        await deleteTemplateContribution(item.id)
        message.success('已删除该贡献')
        loadContributions()
      } catch (err) {
        message.error('删除失败')
      }
    }
  })
}

const formatDate = (dateStr) => {
  if (!dateStr) return '未知'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

const getFullImageUrl = (url) => {
  if (!url) return ''
  return `${apiBaseUrl}${url}`
}

onMounted(() => {
  loadContributions()
})
</script>

<template>
  <div class="flex flex-col">
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-lg font-bold m-0">模板共建管理</h2>
      <a-button @click="loadContributions" :loading="loading">刷新列表</a-button>
    </div>

    <div class="">
      <a-empty v-if="!loading && contributions.length === 0" description="暂无用户提交的模板" />
      
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 p-1">
        <a-card 
          v-for="item in contributions" 
          :key="item.id" 
          hoverable 
          class="contribution-card overflow-hidden"
          :body-style="{ padding: '12px' }"
        >
          <template #cover>
            <div class="relative aspect-[3/4] bg-gray-100 flex items-center justify-center overflow-hidden group cursor-pointer" @click="handlePreview(item)">
              <img 
                v-if="item.file_type === 'photo'"
                :src="getFullImageUrl(item.preview_url)" 
                class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                alt="Template Preview"
              />
              <video 
                v-else-if="item.file_type === 'video'"
                :src="getFullImageUrl(item.preview_url)"
                class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                muted
                loop
                onmouseover="this.play()"
                onmouseout="this.pause(); this.currentTime = 0;"
              ></video>
              <div v-else class="flex flex-col items-center text-gray-400">
                <file-image-outlined style="font-size: 48px" />
                <span class="mt-2">文档文件</span>
              </div>
              
              <!-- Review Status Badge -->
              <div 
                class="absolute top-2 right-2 px-2 py-1 rounded text-xs font-bold shadow-sm"
                :class="item.is_reviewed ? 'bg-green-500 text-white' : 'bg-orange-500 text-white'"
              >
                {{ item.is_reviewed ? '已审核' : '待审核' }}
              </div>

              <!-- Video Icon for video type -->
              <div v-if="item.file_type === 'video'" class="absolute inset-0 flex items-center justify-center">
                <div class="bg-black/30 rounded-full p-3 text-white backdrop-blur-sm group-hover:scale-110 transition-transform">
                  <eye-outlined style="font-size: 24px" />
                </div>
              </div>

              <!-- Overlay Actions -->
              <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-4 text-white font-bold">
                <div class="flex items-center gap-1"><eye-outlined /> 点击预览</div>
              </div>
            </div>
          </template>

          <div class="space-y-2">
            <div class="flex items-center gap-2 text-gray-700">
              <user-outlined class="text-blue-500" />
              <span class="font-medium truncate">{{ item.full_name || item.username || item.user_id }}</span>
            </div>
            
            <div class="flex items-center gap-2 text-gray-400 text-xs">
              <clock-circle-outlined />
              <span>{{ formatDate(item.created_at) }}</span>
            </div>

            <div class="pt-2 flex gap-2">
              <a-button 
                v-if="!item.is_reviewed"
                type="primary" 
                size="small" 
                block
                @click="handleApprove(item)"
                class="flex items-center justify-center gap-1"
              >
                <template #icon><check-outlined /></template>
                采纳
              </a-button>
              <a-button 
                danger 
                size="small" 
                :block="item.is_reviewed"
                :style="{ width: item.is_reviewed ? '100%' : 'auto' }"
                @click="handleDelete(item)"
                class="flex items-center justify-center gap-1"
              >
                <template #icon><delete-outlined /></template>
                {{ item.is_reviewed ? '从库中删除' : '拒绝' }}
              </a-button>
            </div>
          </div>
        </a-card>
      </div>
    </div>

    <!-- Preview Modal -->
    <a-modal
      v-model:visible="previewVisible"
      :footer="null"
      :width="previewType === 'video' ? 800 : 600"
      centered
      @cancel="previewVisible = false"
      class="preview-modal"
    >
      <div class="flex items-center justify-center p-2 mt-4 overflow-hidden">
        <video 
          v-if="previewType === 'video'" 
          :src="previewUrl" 
          controls 
          autoplay 
          class="max-w-full max-h-[80vh] rounded shadow-lg"
        ></video>
        <img 
          v-else 
          :src="previewUrl" 
          class="max-w-full max-h-[80vh] object-contain rounded shadow-lg" 
          alt="Preview" 
        />
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.contribution-card {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid #f0f0f0;
}
.contribution-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 10px 20px rgba(0,0,0,0.08) !important;
}
</style>
