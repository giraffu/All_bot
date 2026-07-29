<script setup lang="ts">
import { useThemeStore } from '@/stores/theme'

useThemeStore().init()
</script>

<template>
  <RouterView />
</template>
