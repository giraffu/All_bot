import glob

files = [
    'src/views/ImageAndPrompt.vue',
    'src/views/FaceSwap.vue',
    'src/views/SingleImage.vue',
    'src/views/SingleImageToVideo.vue',
    'src/views/VideoSwap.vue'
]

ant_style_injection = """
<style scoped>
:deep(.ant-input), :deep(.ant-input-affix-wrapper) {
  background-color: rgba(15, 23, 42, 0.4) !important;
  color: #e2e8f0 !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-input::placeholder) {
  color: #64748b !important;
}
:deep(.ant-upload.ant-upload-drag) {
  background: rgba(15, 23, 42, 0.4) !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-upload.ant-upload-drag:hover) {
  border-color: #3b82f6 !important;
}
:deep(.ant-upload.ant-upload-drag .ant-upload-text) {
  color: #cbd5e1 !important;
}
:deep(.ant-upload.ant-upload-drag .ant-upload-hint) {
  color: #64748b !important;
}
"""

for filepath in files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We replace the beginning of <style scoped> with our injection
    # If <style scoped> doesn't exist, we just append it
    if '<style scoped>' in content:
        content = content.replace('<style scoped>', ant_style_injection)
    else:
        content += '\n' + ant_style_injection + '\n</style>'
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

print("Ant styles injected successfully!")
