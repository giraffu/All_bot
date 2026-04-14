import os
import glob

# Mapping of light theme classes to dark theme classes
class_map = {
    'bg-white': 'bg-slate-800/40 backdrop-blur-md',
    'border-gray-100': 'border-slate-700/50',
    'text-gray-900': 'text-slate-100',
    'text-gray-800': 'text-slate-200',
    'text-gray-700': 'text-slate-300',
    'text-gray-600': 'text-slate-400',
    'text-gray-500': 'text-slate-400',
    'text-gray-400': 'text-slate-500',
    'border-gray-200': 'border-slate-600/50',
    'bg-gray-50': 'bg-slate-900/50',
    'background: #f8fafc;': 'background: rgba(15, 23, 42, 0.4);',
    'bg-black bg-opacity-50': 'bg-black/60',
}

files = [
    'src/views/ImageAndPrompt.vue',
    'src/views/FaceSwap.vue',
    'src/views/SingleImage.vue',
    'src/views/SingleImageToVideo.vue',
    'src/views/VideoSwap.vue'
]

for filepath in files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    for old_cls, new_cls in class_map.items():
        content = content.replace(old_cls, new_cls)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

print("Styles updated successfully!")
