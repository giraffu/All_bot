import os
import re

import os
import glob
import re

MENU_REGEX_STR = r"^(🖼️ 懒人P图|🎬 懒人动图|🔙 返回主菜单|🛌 动图传教士|🎬 动图后入|🎬 口交黑人|🎬 脱衣吐舌|🎬 特写口交|🎨 自由P图|🌟 幻想换脸|💃 快速脱衣|🎭 快速换脸|🥵 快速自慰|🎭 随机换脸|🎬 视频换脸|🎬 自定义视频|🎬 自定义图生视频|📅 每日签到|签到|/checkin|🤝 分享赚灵石|⏳ 排队状态|排队|/queue|💰 个人中心|👤 个人中心|💎 充值灵石|/start)$"

def update_files():
    fsm_dir = "src/handlers/fsm"
    for filepath in glob.glob(os.path.join(fsm_dir, "*.py")):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace the old regex with the new one
        new_content = re.sub(
            r're\.match\(r\'\^\(.*?\)#\', text\)',
            f"re.match(r'{MENU_REGEX_STR}', text)",
            content
        )
        
        new_content = re.sub(
            r"re\.match\(r'\^\(.*?\)#', text\)",
            f"re.match(r'{MENU_REGEX_STR}', text)",
            new_content
        )
        
        # Another common pattern
        new_content = re.sub(
            r"re\.match\(r'\^\(.*?\)#', text\)",
            f"re.match(r'{MENU_REGEX_STR}', text)",
            new_content
        )
        
        # the exact pattern in the files
        new_content = re.sub(
            r"re\.match\(r'\^\(.*?\)#', text\)",
            f"re.match(r'{MENU_REGEX_STR}', text)",
            new_content
        )

        # just replace all re.match for menu regexes in unexpected_input
        pattern_to_find = r"re\.match\(r'\^\(.*?\)#?', text\)"
        
        # Let's do a more robust replacement based on what we saw in grep
        old_regex_pattern = r"re\.match\(r'\^\(.*?\)#?', text\)"
        # actually let's just replace the exact line we know is there
        old_line_pattern = r"re\.match\(r'\^\(🛌 动图传教士.*?/start\)\$', text\)"
        
        new_content = re.sub(old_line_pattern, f"re.match(r'{MENU_REGEX_STR}', text)", content)
        
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated {filepath}")

if __name__ == '__main__':
    update_files()


NEW_UNEXPECTED_INPUT = f"""import re

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and re.match(r'{MENU_REGEX_STR}', text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您自动取消未完成的流程。\\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None"""

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the unexpected_input function
    pattern = r"async def unexpected_input\(update: Update, context: ContextTypes\.DEFAULT_TYPE\) -> int:[\s\S]*?return None"
    
    if re.search(pattern, content):
        new_content = re.sub(pattern, NEW_UNEXPECTED_INPUT, content)
        
        # Add import re if not present
        if "import re" not in new_content:
            new_content = "import re\n" + new_content
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")
    else:
        print(f"Could not find unexpected_input in {filepath}")

fsm_dir = "src/handlers/fsm"
for filename in os.listdir(fsm_dir):
    if filename.endswith("_fsm.py"):
        process_file(os.path.join(fsm_dir, filename))
