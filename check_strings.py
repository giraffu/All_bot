
import re

def check_file(filepath):
    print(f"Checking {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if "懒人P图" in line or "懒人动图" in line:
                print(f"Line {i+1}: {repr(line.strip())}")

check_file(r"e:\1_teleBot\tg_bot\src\handlers\message_handler.py")
check_file(r"e:\1_teleBot\tg_bot\src\handlers\command_handler.py")
