import glob

fsm_files = glob.glob('src/handlers/fsm/*.py')
for filepath in fsm_files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace('from src.constants import (, TMP_DIR', 'from src.constants import TMP_DIR')
    
    # Also some might have just a single import, need to be careful
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
