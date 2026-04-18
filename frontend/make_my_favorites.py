import re

with open('src/views/MySubmissions.vue', 'r') as f:
    content = f.read()

# 1. Replace API endpoint
content = content.replace("await api.get('/gallery/my-posts'", "await api.get('/gallery/my-favorites'")

# 2. Remove toggleStatus and deletePost methods
content = re.sub(r'const toggleStatus = async.*?}\n', '', content, flags=re.DOTALL)
content = re.sub(r'const deletePost = async.*?}\n', '', content, flags=re.DOTALL)

# 3. Remove Top Actions buttons from template
content = re.sub(r'<!-- Top Actions -->.*?</div>\s*<div class="flex flex-wrap', '<div class="flex flex-wrap', content, flags=re.DOTALL)

# 4. Remove is_active badge
content = re.sub(r'<!-- Status & Type Badge -->.*?</div>\s*<!-- Type Badge -->', '<!-- Type Badge -->', content, flags=re.DOTALL)

# 5. Change empty state text
content = content.replace("您还没有投稿任何作品", "您还没有收藏过任何作品")

with open('src/views/MyFavorites.vue', 'w') as f:
    f.write(content)

print("Created MyFavorites.vue")
