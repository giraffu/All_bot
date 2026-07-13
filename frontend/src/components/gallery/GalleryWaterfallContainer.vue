<script setup lang="ts">
import { Waterfall } from 'vue-waterfall-plugin-next'
import 'vue-waterfall-plugin-next/dist/style.css'
import GalleryMediaCard from '@/components/GalleryMediaCard.vue'
import LazyVideo from '@/components/LazyVideo.vue'
import OriginalInputBadge from '@/components/OriginalInputBadge.vue'
import PostCardMetricsBar from '@/components/PostCardMetricsBar.vue'
import PostTagPreview from '@/components/PostTagPreview.vue'
import type { GalleryPost } from '@/types/gallery'
import { getFileUrl } from '@/utils/mediaFiles'
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'

const props = defineProps<{
  posts: GalleryPost[]
  breakpoints: Record<number, { rowPerView: number }>
  isMobile: boolean
  formatTag: (tag: string) => string
}>()

warnIfPropsExceedBudget('GalleryWaterfallContainer', Object.keys(props).length)

const emit = defineEmits<{
  openDetail: [post: GalleryPost]
  imageError: [event: Event, post: GalleryPost]
  interact: [post: GalleryPost, action: 'like' | 'dislike']
  afterRender: []
}>()
</script>

<template>
  <Waterfall
    :list="posts"
    rowKey="id"
    :breakpoints="breakpoints"
    :gutter="isMobile ? 12 : 24"
    :animationDuration="400"
    backgroundColor="transparent"
    :hasAroundGutter="false"
    @afterRender="emit('afterRender')"
  >
    <template #default="{ item: post }">
      <GalleryMediaCard
        :item="post"
        media-container-class="gallery-media-pane relative w-full overflow-hidden"
        :media-container-style="post.width && post.height ? { aspectRatio: `${post.width}/${post.height}` } : { aspectRatio: '1/1' }"
        overlay-visibility-class="opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity duration-300"
        @card-click="emit('openDetail', post)"
      >
        <template #media>
          <img
            v-show="!post.cardIsVideo"
            :src="post.src"
            class="w-full object-cover transition-opacity duration-300 absolute inset-0 h-full"
            loading="lazy"
            @error="emit('imageError', $event, post)"
          />
          <LazyVideo
            v-show="post.cardIsVideo"
            :src="getFileUrl(post.media_url, post.id)"
            :poster="post.cardPoster || post.src"
            className="w-full object-cover absolute inset-0 h-full"
          />
        </template>
        <template #top-left>
          <OriginalInputBadge :source="post" />
        </template>
        <template #overlay>
          <div class="flex flex-col justify-end h-full">
            <PostTagPreview :tags="post.tags" :format-tag="formatTag" />
          </div>
        </template>
        <template #bottom>
          <PostCardMetricsBar
            :likes-count="post.likes_count"
            :dislikes-count="post.dislikes_count"
            :applied-count="post.applied_count"
            :comments-count="post.comments_count"
            :has-liked="post.has_liked"
            :has-disliked="post.has_disliked"
            show-comments
            @like="emit('interact', post, 'like')"
            @dislike="emit('interact', post, 'dislike')"
            @comment="emit('openDetail', post)"
          />
        </template>
      </GalleryMediaCard>
    </template>
  </Waterfall>
</template>

<style scoped>
.gallery-media-pane {
  background: var(--theme-card-strong-bg);
}
</style>
