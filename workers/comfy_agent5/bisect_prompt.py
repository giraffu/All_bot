import json, requests

def test_prompt(wf, name):
    resp = requests.post('http://192.168.1.226:8188/prompt', json={"prompt": wf}).json()
    q = requests.get('http://192.168.1.226:8188/queue').json()["queue_pending"][-1][4]
    print(f"{name}: {'61' in q}")
    requests.post('http://192.168.1.226:8188/queue', json={"delete": [resp["prompt_id"]]})

good = json.load(open('test_prompt.json'))
test_prompt(good, "Original Good")

good["18"]["inputs"]["Xf"] = 10.0
test_prompt(good, "Xf = 10.0")

good["15"]["inputs"]["image"] = "127e65cf-f30c-4705-8baf-7b9fa25be938.png"
test_prompt(good, "image = png")

good["28"]["inputs"]["text"] = "Selfie-style closeup video of a young chinese woman The girl in the picture slowly takes off her clothes and is completely naked. the camera slowly zooms in to a low angle extreme close-up on her detailed pussy and anus and wet vaginal opening from behind as he ass is exposed. she playfully says \"is this what you want to eat?\""
good["29"]["inputs"]["text"] = good["28"]["inputs"]["text"]
test_prompt(good, "long text")

good["59"]["inputs"]["filename_prefix"] = "MrXin/LTX2.3/I2V/FirstPass"
good["61"]["inputs"]["filename_prefix"] = "MrXin/LTX2.3/I2V/Final"
test_prompt(good, "filename_prefix")

good["26:49"]["inputs"]["cfg"] = 1.0
test_prompt(good, "cfg = 1.0")

actual = json.load(open('actual_prompt.json'))
test_prompt(actual, "Actual")

good2 = json.load(open('test_prompt.json'))
# Let's apply ALL changes except the SEED!
good2["18"]["inputs"]["Xf"] = 10.0
good2["19"]["inputs"]["Xf"] = 704.0
good2["181"]["inputs"]["Xf"] = 1280.0
good2["15"]["inputs"]["image"] = "127e65cf-f30c-4705-8baf-7b9fa25be938.png"
good2["28"]["inputs"]["text"] = good["28"]["inputs"]["text"]
good2["29"]["inputs"]["text"] = good["28"]["inputs"]["text"]
good2["59"]["inputs"]["filename_prefix"] = "MrXin/LTX2.3/I2V/FirstPass"
good2["61"]["inputs"]["filename_prefix"] = "MrXin/LTX2.3/I2V/Final"
good2["26:49"]["inputs"]["cfg"] = 1.0
good2["26:90"]["inputs"]["cfg"] = 1.0
good2["26:44"]["inputs"]["strength"] = 1.0
good2["26:87"]["inputs"]["strength"] = 1.0
good2["26:93"]["inputs"]["value"] = 0.0
good2["26:65"]["inputs"]["value"] = 0.0

test_prompt(good2, "All changes except seed")

good2["125"]["inputs"]["seed"] = 7539147734634328
test_prompt(good2, "All changes including seed")

