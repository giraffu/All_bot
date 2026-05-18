import os
import glob
import re

fsm_files = glob.glob('src/handlers/fsm/*.py')
for filepath in fsm_files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if '/tmp/bot_fsm_tmp' in content:
        # Import TMP_DIR if not already imported
        if 'from src.constants import' in content and 'TMP_DIR' not in content:
            content = re.sub(r'from src\.constants import (.*?)\n', r'from src.constants import \1, TMP_DIR\n', content, count=1)
        elif 'from src.constants import TMP_DIR' not in content:
            content = 'from src.constants import TMP_DIR\n' + content
            
        content = content.replace('"/tmp/bot_fsm_tmp"', 'TMP_DIR')
        content = content.replace('f"/tmp/bot_fsm_tmp/{', 'os.path.join(TMP_DIR, f"{')
        content = content.replace('_quick.png"', '_quick.png")')
        content = content.replace('_ref.png"', '_ref.png")')
        content = content.replace('_face.png"', '_face.png")')
        content = content.replace('_body.png"', '_body.png")')
        content = content.replace('_qvid.png"', '_qvid.png")')
        content = content.replace('_video_lora.png"', '_video_lora.png")')
        content = content.replace('_ltx_vid.png"', '_ltx_vid.png")')
        content = content.replace('_video.mp4"', '_video.mp4")')
        content = content.replace('_custom_vid.png"', '_custom_vid.png")')

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")
