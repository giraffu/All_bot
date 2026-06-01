---
name: vue-best-practices
description: "MUST be used for Vue.js tasks. Strongly recommends Composition API with script setup and TypeScript as the standard approach. Covers Vue 3, SSR, Volar, vue-tsc. Load for any Vue, .vue files, Vue Router, Pinia, or Vite with Vue work. ALWAYS use Composition API unless the project explicitly requires Options API."
---

# Vue Best Practices

## 1. 核心规范 (Core Principles)
- **Composition API First**：所有新组件必须使用 `<script setup lang="ts">`，全面弃用 Options API。
- **TypeScript 强类型**：使用 TypeScript 声明 `defineProps`、`defineEmits` 和所有响应式数据的类型。
- **状态管理**：使用 Pinia 替代 Vuex。

## 2. 国际化架构 (i18n Architecture)
本系统实行**前后端文案隔离红线**：
- **禁止后端硬编码文案**：API（如 `UserDashboardDTO`）仅允许返回状态枚举、布尔值及原始数值。绝对禁止在后端组合拼接带有 emoji 或中文的格式化字符串。
- **前端负责所有展示逻辑**：基于 `vue-i18n` 实现文案的多语言渲染。

### 示例 (最佳实践)
**Bad (后端返回硬编码文本)**:
```json
{ "invite_msg": "🎉 恭喜！您已邀请 3/5 人" }
```

**Good (后端返回原始数据，前端负责渲染)**:
```json
// Backend DTO
{ "invite_count": 3, "invite_target": 5 }
```
```vue
<!-- Frontend Vue Component -->
<template>
  <div>{{ t('dashboard.invite_progress', { count: data.invite_count, target: data.invite_target }) }}</div>
</template>
```
