import re

with open('/home/hfy/APP/All_bot/frontend/src/views/MySubmissions.vue', 'r') as f:
    content = f.read()

# Update interface
content = content.replace(
    'has_disliked: boolean\n}',
    'has_disliked: boolean\n  is_active: boolean\n  prompt: string\n}'
)

# Remove imports
content = content.replace("import { Heart, ThumbsDown, Wand2, Play, Image as ImageIcon, Video, Flame, Clock } from 'lucide-vue-next'", 
                          "import { Heart, ThumbsDown, Wand2, Play, Image as ImageIcon, Video, Flame, Clock, Trash2, Eye, EyeOff, Copy } from 'lucide-vue-next'")

# Update loadPosts endpoint and params
load_posts_orig = """    const res = await api.get('/gallery/posts', {
      params: {
        page: page.value,
        size: size.value,
        media_type: mediaType.value,
        task_type: taskType.value,
        lora_model: loraModel.value === 'all' ? undefined : loraModel.value,
        sort_by: sortBy.value,
        time_range: timeRange.value
      }
    })"""
load_posts_new = """    const res = await api.get('/gallery/my-posts', {
      params: {
        page: page.value,
        size: size.value
      }
    })"""
content = content.replace(load_posts_orig, load_posts_new)

# Add new functions
new_functions = """
const toggleStatus = async (post: Post) => {
  try {
    const newStatus = !post.is_active
    await api.put(`/gallery/posts/${post.id}/status`, null, {
      params: { is_active: newStatus }
    })
    post.is_active = newStatus
    message.success(`已${newStatus ? '上架' : '下架'}`)
  } catch (error) {
    console.error(error)
    message.error('操作失败')
  }
}

const deletePost = async (post: Post) => {
  if (!confirm('确定要删除这条投稿吗？')) return
  try {
    await api.delete(`/gallery/posts/${post.id}`)
    posts.value = posts.value.filter(p => p.id !== post.id)
    message.success('删除成功')
  } catch (error) {
    console.error(error)
    message.error('删除失败')
  }
}

const copyPrompt = (post: Post) => {
  if (!post.prompt) {
    message.warning('此投稿没有提示词')
    return
  }
  navigator.clipboard.writeText(post.prompt).then(() => {
    message.success('提示词已复制到剪贴板')
  }).catch(() => {
    message.error('复制失败')
  })
}
"""

content = content.replace("const handleApply = async () => {", new_functions + "\nconst handleApply = async () => {")

# Remove header controls (filters)
header_controls_start = "<!-- Header Controls -->"
header_controls_end = "<!-- Masonry Grid -->"
content = re.sub(r'<!-- Header Controls -->.*?<!-- Masonry Grid -->', '<!-- Masonry Grid -->', content, flags=re.DOTALL)

# Add actions to card
card_overlay_start = "<!-- Tags Overlay on Hover -->"
card_overlay_new = """<!-- Tags Overlay on Hover -->
          <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-between p-4">
            <!-- Top Actions -->
            <div class="flex justify-end gap-2">
              <button @click.stop="toggleStatus(post)" class="p-2 rounded-full bg-black/50 hover:bg-black/80 text-white backdrop-blur-sm transition-all" :title="post.is_active ? '点击下架' : '点击上架'">
                <Eye v-if="post.is_active" :size="16" class="text-green-400" />
                <EyeOff v-else :size="16" class="text-orange-400" />
              </button>
              <button @click.stop="deletePost(post)" class="p-2 rounded-full bg-black/50 hover:bg-red-500/80 text-white backdrop-blur-sm transition-all" title="删除投稿">
                <Trash2 :size="16" />
              </button>
            </div>
            
            <div class="flex flex-wrap gap-1.5 mb-8">
              <span v-for="tag in post.tags.slice(0, 4)" :key="tag" class="text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md">
                {{ tag }}
              </span>
              <span v-if="post.tags.length > 4" class="text-[10px] text-slate-300 px-1">...</span>
            </div>
          </div>"""
content = content.replace(card_overlay_start + """
          <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-4">
            <div class="flex flex-wrap gap-1.5 mb-8">
              <span v-for="tag in post.tags.slice(0, 4)" :key="tag" class="text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md">
                {{ tag }}
              </span>
              <span v-if="post.tags.length > 4" class="text-[10px] text-slate-300 px-1">...</span>
            </div>
          </div>""", card_overlay_new)

# Add status badge
type_badge_orig = "<!-- Type Badge -->"
type_badge_new = """<!-- Status & Type Badge -->
          <div class="absolute top-2 left-2 flex items-center gap-2">
            <div class="bg-black/60 backdrop-blur-sm rounded-full px-2 py-1 shadow-sm border border-white/10 text-xs font-bold" :class="post.is_active ? 'text-green-400' : 'text-orange-400'">
              {{ post.is_active ? '已上架' : '已下架' }}
            </div>
          </div>
          <!-- Type Badge -->"""
content = content.replace(type_badge_orig, type_badge_new)

# Add prompt copy button in modal
modal_actions_orig = """<div class="mt-8">
            <button 
              @click="handleApply" """
modal_actions_new = """<div class="mt-8 space-y-4">
            <button v-if="currentPost.prompt"
              @click="copyPrompt(currentPost)"
              class="w-full py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-medium shadow-sm transition-all flex items-center justify-center border border-slate-600"
            >
              <Copy :size="18" class="mr-2" />
              复制提示词 (Prompt)
            </button>
            <button 
              @click="handleApply" """
content = content.replace(modal_actions_orig, modal_actions_new)

# Fix empty state text
content = content.replace("暂无道友分享作品", "您还没有投稿任何作品")

with open('/home/hfy/APP/All_bot/frontend/src/views/MySubmissions.vue', 'w') as f:
    f.write(content)

print("Done")
