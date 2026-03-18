import re

with open('/home/hfy/APP/All_bot/src/bot_test.py', 'r') as f:
    content = f.read()

content = content.replace('await qm.clear_temp_credits()', 'await qm.clear_temp_credits()\n    await qm.clear_temporary_ingots()')

with open('/home/hfy/APP/All_bot/src/bot_test.py', 'w') as f:
    f.write(content)
