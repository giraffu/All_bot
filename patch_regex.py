import os
import glob
import re

search_str = r"^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|🎬 图生视频\(附加模型\)|🎬 高级图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start|🏆 发现/排行榜|一键应用该模板)$"
replace_str = r"^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|🖼️ 图生图\(附加模型\)|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|🎬 图生视频\(附加模型\)|🎬 高级图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start|🏆 发现/排行榜|一键应用该模板)$"

for fpath in glob.glob("/home/hfy/APP/All_bot/src/handlers/fsm/*.py"):
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    if search_str in content:
        content = content.replace(search_str, replace_str)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Patched {fpath}")
    else:
        print(f"Skipped {fpath}")
