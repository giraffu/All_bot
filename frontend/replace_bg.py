import re
import glob

vue_files = glob.glob("/home/hfy/APP/All_bot/frontend/src/**/*.vue", recursive=True)

bg_pattern = re.compile(r"bg-slate-[789]00(?:/(\d+))?")
border_pattern = re.compile(r"border-slate-[678]00(?:/(\d+))?")

for file in vue_files:
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()

    def bg_repl(match):
        opacity = match.group(1)
        if opacity:
            # If opacity is 40 or 50, maybe make it 50. Let's just keep original opacity or default to 50 if it was 40.
            # Actually, just keeping the original opacity is fine, but slate-500/40 might be a bit light. Let's just use 50.
            if opacity in ["40", "50"]:
                return "bg-slate-500/50"
            return f"bg-slate-500/{opacity}"
        else:
            # no opacity
            return "bg-slate-500"

    def border_repl(match):
        opacity = match.group(1)
        if opacity:
            return f"border-slate-400/{opacity}"
        else:
            return "border-slate-400"

    new_content = bg_pattern.sub(bg_repl, content)
    new_content = border_pattern.sub(border_repl, new_content)

    if new_content != content:
        with open(file, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated {file}")
