import os
import glob

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "if not await permission_service.check_quota" in line:
            # We assume it takes 3 lines:
            # if not await permission_service.check_quota(...):
            #     _cleanup_context(...)
            #     return ConversationHandler.END
            # Replace with try-except block
            indent = line[:len(line) - len(line.lstrip())]
            call = line.replace("if not await", "await").replace(":\n", "\n").lstrip()
            
            try_block = [
                f"{indent}try:\n",
                f"{indent}    {call}",
                f"{indent}except Exception as e:\n",
                f"{indent}    from src.core.exceptions import InsufficientCreditsError\n",
                f"{indent}    if isinstance(e, InsufficientCreditsError):\n",
                f"{indent}        chat_id = update.effective_chat.id\n",
                f"{indent}        msg = f\"🚫 **灵石不足**\\n\\n道友当前余额: `{{e.current}}` 灵石\\n本次修炼需要: `{{e.cost}}` 灵石\\n请联系管理员获取更多灵石。\"\n",
                f"{indent}        from src.utils import robust_send_message\n",
                f"{indent}        await robust_send_message(context.bot, chat_id, msg, parse_mode=\"Markdown\")\n"
            ]
            
            # Now we look at the next lines to get the cleanup and return
            j = i + 1
            while j < len(lines) and lines[j].strip() != "" and lines[j].startswith(indent + "    "):
                try_block.append(f"{indent}        {lines[j].lstrip()}")
                j += 1
                
            try_block.append(f"{indent}    raise e\n")
            new_lines.extend(try_block)
            i = j
        else:
            new_lines.append(line)
            i += 1
            
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

for filepath in glob.glob("src/handlers/fsm/*.py"):
    fix_file(filepath)

fix_file("src/handlers/callbacks/misc_callbacks.py")
