import os
import re

directory = "/home/hfy/APP/All_bot/src/handlers/fsm"
# First revert the space typos:
for filename in os.listdir(directory):
    if filename.endswith("_fsm.py"):
        filepath = os.path.join(directory, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # fix typos
        content = content.replace("脱衣 吐舌", "脱衣吐舌")
        content = content.replace("排队状 态", "排队状态")

        # Now, inject the same check at the top of receive_prompt
        # receive_prompt usually starts with:
        # async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        #     user_id = update.effective_user.id
        #     message = update.message
        #     prompt = message.text.strip()
        
        # We want to add the check right after `prompt = message.text.strip()` or similar.
        # But wait, it's safer to just inject it at the beginning of `receive_prompt`.
        
        pattern_receive_prompt = r"(async def receive_prompt.*?-> int:\n(?:\s+.*?\n){1,5}?)(?=\s+fsm_data |\s+image_path |\s+base_cost )"
        
        # Let's just use string replace since there are only 4 files.
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
