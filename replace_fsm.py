import os

directory = "/home/hfy/APP/All_bot/src/handlers/fsm/"
old_str1 = "re.match(r'^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|🎬 图生视频\(附加模型\)|🎬 高级图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start|🏆 发现/排行榜|一键应用该模板)$', text)"
new_str1 = "is_global_menu_command(text)"

old_str2 = "re.match(r'^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|🎬 图生视频\(附加模型\)|🎬 高级图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start|🏆 发现/排行榜|一键应用该模板)$', prompt)"
new_str2 = "is_global_menu_command(prompt)"

for filename in os.listdir(directory):
    if filename.endswith(".py"):
        filepath = os.path.join(directory, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        new_content = content.replace(old_str1, new_str1).replace(old_str2, new_str2)
        
        if new_content != content:
            if "from src.handlers.prompt_router import is_global_menu_command" not in new_content:
                lines = new_content.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith("from telegram") or line.startswith("import"):
                        lines.insert(i, "from src.handlers.prompt_router import is_global_menu_command")
                        break
                new_content = '\n'.join(lines)
                
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"Updated {filename}")
