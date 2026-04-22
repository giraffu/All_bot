import json, requests
wf = json.load(open('actual_prompt.json'))
resp = requests.post('http://192.168.1.226:8188/prompt', json={"prompt": wf}).json()
print("Prompt ID:", resp["prompt_id"])
import time
time.sleep(2)
hist = requests.get(f'http://192.168.1.226:8188/history/{resp["prompt_id"]}').json()
if resp["prompt_id"] in hist:
    print("Executed outputs:", hist[resp["prompt_id"]]["prompt"][4])
    print("Status:", hist[resp["prompt_id"]]["status"])
else:
    print("Still running")
