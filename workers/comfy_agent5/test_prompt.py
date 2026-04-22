import json
import requests
wf = json.load(open('/home/hfy/APP/All_bot/workers/comfy_agent1/workflows/LTX 2.3 I2V.json'))
resp = requests.post('http://192.168.1.226:8188/prompt', json={"prompt": wf})
print(resp.json())
