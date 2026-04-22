import json, time, requests
wf = json.load(open('/home/hfy/APP/All_bot/workers/comfy_agent1/workflows/LTX 2.3 I2V.json'))
resp = requests.post('http://192.168.1.226:8188/prompt', json={"prompt": wf}).json()
prompt_id = resp["prompt_id"]
print("Prompt ID:", prompt_id)
time.sleep(2)
hist = requests.get(f'http://192.168.1.226:8188/history/{prompt_id}').json()
if prompt_id in hist:
    print("Executed outputs:", hist[prompt_id]["prompt"][4])
else:
    print("Still running... check queue")
    queue = requests.get('http://192.168.1.226:8188/queue').json()
    for q in queue["queue_running"] + queue["queue_pending"]:
        if q[1] == prompt_id:
            print("Outputs to execute:", q[4])
