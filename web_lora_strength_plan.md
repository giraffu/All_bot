# Web端自由P图附加模型强度动态适配与自定义方案

## 1. 现状与目标
**现状**：
目前在 Web 端（`ImageAndPrompt.vue`）的【自由P图】功能中，当用户选择附加模型（LoRA）时，前端向后端提交的 `lora_strength` 被硬编码为 `0.3`。这导致了平胸、扶他等需要高强度（如 `0.8`）的模型无法发挥应有的作用。

**目标**：
1. **智能默认值适配**：将 Bot 端 `edit_image_fsm.py` 中的默认模型强度逻辑同步到 Web 端。当用户切换模型时，自动将滑块跳至该模型的最佳默认强度。
2. **允许用户自定义**：在 Web 端的 UI 中增加强度调节滑块，允许高阶用户覆盖默认值，进行细粒度控制。

## 2. 涉及修改的文件
- `frontend/src/views/ImageAndPrompt.vue` (自由P图 Web 端页面)

## 3. 具体实施步骤

### 3.1 增加强度映射与响应式变量 (Script 层面)
在 `<script setup lang="ts">` 中，定义默认强度映射，并增加一个响应式变量 `customLoraStrength` 来绑定 UI 滑块。

```typescript
// 1. 定义与 Bot 端一致的默认强度字典
const LORA_DEFAULT_STRENGTHS: Record<string, number> = {
  'qwen/YARN_1.0.safetensors': 0.3,
  'qwen/adjust_pussy_anus.safetensors': 1.0, // Bot 端 default 兜底是 1.0
  'qwen/realistic_texture.safetensors': 0.8,
  'qwen/flat_chest_hairless.safetensors': 0.8,
  'qwen/penis.safetensors': 0.7
}

// 2. 绑定 UI 的响应式变量，默认设为 1.0
const customLoraStrength = ref<number>(1.0)
```

### 3.2 监听模型切换动态更新默认值 (Watcher) 与模板应用 (onMounted)
**注意 Vue 的 watch 异步执行陷阱**：必须拦截模板应用状态，防止 watch 异步触发时用默认值覆盖掉克隆带来的参数。

```typescript
// 监听选中的 LoRA，自动切换推荐的强度
watch(selectedLora, (newLora) => {
  // 增加拦截：如果是加载了模板，不要用默认值覆盖模板带来的强度参数
  if (isTemplateApplied.value) return 

  if (newLora) {
    // 如果字典中有配置，则使用配置值；否则使用默认值 1.0
    customLoraStrength.value = LORA_DEFAULT_STRENGTHS[newLora] || 1.0
  }
})
```

在 `onMounted` 模板应用的逻辑中，显式读取并设置强度（注意由于后端 `History` 暂未存储 `lora_strength`，必须兜底使用推荐值）：
```typescript
// 现有 onMounted 中的代码
if (ctx.task_type === taskType.value) {
  if (ctx.prompt) prompt.value = ctx.prompt
  if (ctx.lora_name) {
    selectedLora.value = ctx.lora_name
    
    // 【核心修正】：因为后端 ApplyContextResponse 目前没有 lora_strength 字段
    // 当发生一键克隆时，我们强制回退到该模型的最佳默认推荐值，防止 1.0 的灾难发生
    customLoraStrength.value = ctx.lora_strength !== undefined 
      ? Number(ctx.lora_strength) 
      : (LORA_DEFAULT_STRENGTHS[ctx.lora_name] || 1.0)
  }
  isTemplateApplied.value = true
}
```

### 3.3 修改提交参数 (Payload)
在 `handleGenerate` 方法中，移除硬编码的 `0.3`，改为使用用户当前的 `customLoraStrength.value`。

```typescript
  if (payload.task_type === 'img2img_lora') {
    payload.inputs.lora_name = selectedLora.value
    // 移除旧的: payload.inputs.lora_strength = 0.3
    // 替换为:
    payload.inputs.lora_strength = Number(customLoraStrength.value)
  }
```

### 3.4 增加 UI 滑块组件 (Template 层面)
在模板中找到“附加模型 (LoRA)”的区域，在单选按钮下方增加一个控制强度的 Slider。
使用 Ant Design Vue 的 `<a-slider>` 和 `<a-input-number>`，并在无模型被选中时隐藏该滑块。

```html
<div v-if="taskType === 'edit'" class="w-full bg-slate-500/60 rounded-xl p-4 border border-slate-400/50 shrink-0">
  <h3 class="text-sm font-bold mb-3 text-slate-200 flex items-center">
    <span class="text-slate-500 mr-2">0.</span> 附加模型 (LoRA)
  </h3>
  <div class="flex flex-wrap gap-3 mb-4">
    <a-radio-group v-model:value="selectedLora" button-style="solid" class="w-full sm:w-auto" :disabled="isTemplateApplied">
      <a-radio-button v-for="option in loraOptions" :key="option.value" :value="option.value" class="text-center">
        {{ option.label }}
      </a-radio-button>
    </a-radio-group>
  </div>
  
  <!-- 新增：强度自定义滑块 (仅在选中了具体模型时显示) -->
  <div v-if="selectedLora" class="flex flex-col mt-4 pt-4 border-t border-slate-500/50">
    <div class="flex justify-between items-center mb-2">
      <span class="text-xs text-slate-300">模型强度 (Lora Strength)</span>
      <span class="text-xs text-slate-400">推荐值已自动适配</span>
    </div>
    <div class="flex items-center gap-4">
      <a-slider 
        v-model:value="customLoraStrength" 
        :min="0.1" 
        :max="2.0" 
        :step="0.05" 
        class="flex-grow"
        :disabled="isTemplateApplied"
      />
      <a-input-number 
        v-model:value="customLoraStrength" 
        :min="0.1" 
        :max="2.0" 
        :step="0.05" 
        class="w-20 bg-slate-800/50 border-slate-400/50 text-slate-200"
        size="small"
        :disabled="isTemplateApplied"
      />
    </div>
  </div>
</div>
```

### 3.5 表单重置逻辑 (体验优化)
在 `resetForm` 方法中，顺手将强度重置回默认值，避免上一次手动调节的极端参数影响下一次操作。

```typescript
const resetForm = () => {
  // ... 现有代码
  uploadedImages.value = []
  prompt.value = ''
  selectedLora.value = '' // 可选，重置模型选择
  customLoraStrength.value = 1.0 // 补充：重置模型强度
  setSubmittedTaskId(null)
}
```

## 4. UI/UX 细节建议
1. **禁用态同步**：当用户通过广场的“一键克隆 (Apply)”带入了特定的模型和参数时，UI 上的 `isTemplateApplied` 应当把 Slider 也禁用，防止破坏模板的原有效果。
2. **Slider 范围**：建议设置为 `0.1` 到 `2.0`（通常 `1.0` 是 100% 强度，超过 `2.0` 画面容易崩坏），步长为 `0.05` 方便微调。
3. **样式适配**：确保新增的 `a-slider` 和 `a-input-number` 组件的深色模式样式与现有的 `ImageAndPrompt.vue` Tailwind 深色系相匹配。由于 `<a-input-number>` 结构复杂，需要在 `<style scoped>` 中追加以下样式覆盖：

```css
:deep(.ant-input-number) {
  background-color: rgba(15, 23, 42, 0.4) !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
  color: #e2e8f0 !important;
}
:deep(.ant-input-number-input) {
  color: #e2e8f0 !important;
}
:deep(.ant-input-number-handler-wrap) {
  background-color: rgba(15, 23, 42, 0.6) !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-input-number-handler) {
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-input-number-handler-up-inner),
:deep(.ant-input-number-handler-down-inner) {
  color: #94a3b8 !important;
}
```