This is a complete re-haul of the dataset from scratch. Triggerword: PENISLORA

Donate to my kofi and I can train an i2v optimized version.

Dataset

I took out all the images and this was trained purely on video. Due to the issues we had with motion before. Next I went through the dataset and anything low resolution (640x) I put into its own bucket group because training them on higher resolution gave blurry penis heads. Also because 9:16 videos train weird, I converted all those to cropped 4:3 or 16:9 with black bars. This left me with 4 groups: HD 16:9 / 4:3 and LOW Res 16:9 / 4:3 (1280x704, 1088x832 on HD, and 640x360, 640x480 on Low res). The newly added data was mostly 121 frame clips. So a majority of our data is trained on high resolution and longer. I created a whole new tool to both trim clips and crop them. And I used mradermacher's Qwen3.5-27B-heretic-GGUF with my captioning tool to caption the new clips. And I am blown away by how good this was at captioning NSFW. Gemini is still better but it can only do SFW dataset captioning. I recommend you check this model out.

Training
Trained on Musubi Fork by Akane on ltx2.3 branch. So I had run this for like 5 days straight tweaking the dataset as I went. And then suddenly LTX 2.3 dropped. So I scrapped the LTX 2.0 working version and started from 0 but with the ideal settings. I accidentally trained the audio on LTX2.0 version and it sounds great despite not being captioned. So I might do V2 on LTX2.3 with sound next so understand V1 is not trained on audio. It took around 24 hours of straight training to reach 17.5K steps at 6s/it. I think maybe I should've trained lower resolution to speed things up, but the result was good. We got detail on the penis head around 15K steps in. The shaft and motion were pretty solid from 4K steps in. Around 17.5K we started seeing raising in avg loss and worse result so I stuck with 17K, though the 16.5K checkpoint was also good.

Prompting

Same as old versions. Use PENISLORA trigger at front. The word for penis is "Penis". Not trained on flaccid penis and most penis in the dataset are circumcised. You can also prompt "Penis shown from the front" or "penis shown from the side". "Blow job" is captioned and as is "deepthroat" but there is not a ton of data so YMMV. I think maybe cum is captioned partially but I tried to remove this from the dataset as I think it will need a separate lora for that, but give it a try (if its still in the dataset it would be "cum shoots from the penis"). If penis has no action you can state "the man's penis is exposed". Use "the man strokes his penis" or "the woman strokes the man's penis" for jerking or hand jobs.

Known Issues

Sometimes penis head doesn't come out right, especially with showing from odd angles. Try different seeds. The penis may be super bouncy, this was due to some poor captioning on data where the penis was not being stroked or sucked. I think easy to fix in v2. Nipples may not be great. Sometimes breasts are weird. Try to use a different lora to fix that. You probably will get random penis on women if they're nude. Maybe try a different lora to fix that. Will try to fix in future versions these problems. It may be a bit overcooked. Let me know, I can try to give earlier checkpoints.

Description
This is a complete re-haul of the dataset from scratch.

Dataset

I took out all the images and this was trained purely on video. Due to the issues we had with motion before. Next I went through the dataset and anything low resolution (640x) I put into its own bucket group because training them on higher resolution gave blurry penis heads. Also because 9:16 videos train weird, I converted all those to cropped 4:3 or 16:9 with black bars. This left me with 4 groups: HD 16:9 / 4:3 and LOW Res 16:9 / 4:3 (1280x704, 1088x832 on HD, and 640x360, 640x480 on Low res). The newly added data was mostly 121 frame clips and total 215 clips. So a majority of our data is trained on high resolution and longer. I created a whole new tool to both trim clips and crop them. And I used mradermacher's Qwen3.5-27B-heretic-GGUF with my captioning tool to caption the new clips. And I am blown away by how good this was at captioning NSFW. Gemini is still better but it can only do SFW dataset captioning. I recommend you check this model out.

Training
Trained on Musubi Fork by Akane on ltx2.3 branch. So I had run this for like 5 days straight tweaking the dataset as I went. And then suddenly LTX 2.3 dropped. So I scrapped the LTX 2.0 working version and started from 0 but with the ideal settings. I accidentally trained the audio on LTX2.0 version and it sounds great despite not being captioned. So I might do V2 on LTX2.3 with sound next so understand V1 is not trained on audio. It took around 24 hours of straight training to reach 17.5K steps at 6s/it. I think maybe I should've trained lower resolution to speed things up, but the result was good. We got detail on the penis head around 15K steps in. The shaft and motion were pretty solid from 4K steps in. Around 17.5K we started seeing raising in avg loss and worse result so I stuck with 17K, though the 16.5K checkpoint was also good.

Prompting

Same as old versions. Use PENISLORA trigger at front. The word for penis is "Penis". Not trained on flaccid penis and most penis in the dataset are circumcised. You can also prompt "Penis shown from the front" or "penis shown from the side". "Blow job" is captioned and as is "deepthroat" but there is not a ton of data so YMMV. I think maybe cum is captioned partially but I tried to remove this from the dataset as I think it will need a separate lora for that, but give it a try (if its still in the dataset it would be "cum shoots from the penis"). If penis has no action you can state "the man's penis is exposed". Use "the man strokes his penis" or "the woman strokes the man's penis" for jerking or hand jobs.

Known Issues

Sometimes penis head doesn't come out right, especially with showing from odd angles. Try different seeds. The penis may be super bouncy, this was due to some poor captioning on data where the penis was not being stroked or sucked. I think easy to fix in v2. Nipples may not be great. Sometimes breasts are weird. Try to use a different lora to fix that. You probably will get random penis on women if they're nude. Maybe try a different lora to fix that. Will try to fix in future versions these problems. It may be a bit overcooked. Let me know, I can try to give earlier checkpoints.

FAQ
What is Penis Lora - LTX 2.3?
Penis Lora - LTX 2.3 is a style LoRA designed for LTX Video-family checkpoints, published by tazmannner379 on CivitAI in January 2026, now on version 7. It layers on top of any compatible LTX Video checkpoint. You load the checkpoint first, then apply this LoRA on top of it. It has attracted 3,448 downloads. The model is flagged NSFW on CivitAI and can produce explicit content.

Why was this model removed from CivitAI?
It was removed from CivitAI in April 2026 after accumulating 3,448 downloads. CivitAI began bulk-removing content in April 2025 after Visa's VAMP program tightened adult-AI compliance rules, fined CivitAI's merchant bank (Esquire Bank / ECSuite), and forced a choice between stricter content policy and losing card processing. May 2025 escalated further — an automated tagging system (Clavata) flagged adult uploads aggressively, a formal real-person likeness removal policy wiped celebrity and historical-figure LoRAs, and the platform announced a full credit-card processing ban with only months of runway left. Removals from this period are almost always platform-driven, not author-driven. CivArchive tracks files by their SHA256 hash, so the mirrors listed on this page may still let you download it even though the original page is gone. That is the whole point of this archive.

How do I use Penis Lora - LTX 2.3?
Triggers. This LoRA activates with the following trigger word: PENISLORA. Include them in your positive prompt to pull the trained concept into the output. Without the trigger, the LoRA still has some effect, but it is usually much weaker.

Prompting. LTX Video uses natural-language sentences. LTX is notably prompt-sensitive and rewards longer, more detailed prompts than competitors. Motion-focused action verbs and specific descriptive language work better than short prompts. Users commonly employ external LLMs (ChatGPT, Grok) to enhance prompts or use multimodal vision models to analyze input images and generate video-appropriate descriptions. Add the trigger word (PENISLORA) alongside your normal prompt.

Weight. A good starting weight for most LoRAs is around 0.8, and the typical useful range is 0.6 to 0.9. From there, adjust based on what you see:

Too strong (bleeding into everything, distorted anatomy): drop to 0.5 to 0.7
Too weak (no visible effect): push to 0.9 to 1.0
Style LoRAs often want lower weights (0.5 to 0.7) than character LoRAs
If the author's description lists a recommended range, prefer that. They know their own training best.

Compatible checkpoints. Any LTX Video-family checkpoint should work. Popular choices include LTXV 0.9.7, LTXV 0.9.6, LTX-2, Wan Video 2.2, and Hunyuan Video. Results vary by checkpoint, since a LoRA tuned against one finetune's aesthetic may look different on another even when the base family matches.

Base settings. Distilled models run optimally at 8 steps, while dev models require 25 or more steps for comparable quality. Common resolution defaults are 768x512 or the official 1216x704 at 30 fps (as of 0.9.6). CRF compression values of 30 to 40 are recommended for balancing quality and motion clarity. Spatio-Temporal Guidance (STG) can enhance results but over-application produces an unnatural look. CFG scaling and step counts differ significantly between distilled and dev checkpoints, with distilled offering stability over prompt adherence and dev offering the reverse.

Loading it. Video LoRAs are ComfyUI-only in practice. Save the file to models/loras/ and load it with a Load LoRA node (or Load LoRA Model Only in setups that route model and CLIP separately) placed between the checkpoint loader and the sampler in your video workflow. Chain multiple Load LoRA nodes to stack LoRAs. Automatic1111 and Forge do not run video models.

Why might this LoRA not be producing the expected results?
Four things cause most LoRA problems. Run through them in order:

Wrong base model. LoRAs are tied to the base they were trained on. A Pony LoRA on an Illustrious checkpoint will silently produce weak or broken results even though it loads without error.
Missing trigger words. If this version lists triggers, they usually need to be in the positive prompt.
Wrong weight. At 0.3 the effect may be invisible; at 1.2 it may overwhelm everything else. Start at 0.8 and adjust.
Checkpoint conflict. Some heavily styled checkpoints fight LoRAs that pull in a different direction. Try the author's recommended checkpoint if one is mentioned, or a vanilla base in the same family.
If none of these fix it, check the version you downloaded matches the version the author's examples were generated with — updates sometimes break earlier trigger words or require retrained replacements.

Can I use this LoRA commercially?
LoRAs inherit the license of their base model. LTX-2 uses a community license that permits free use for non-commercial purposes and for businesses under a $10M annual revenue threshold. Above that threshold, a paid commercial license is required. Earlier LTXV releases are under RAIL-M-family terms.

What files are available and where can I download them?
This version ships as a 504 MB safetensors file (plora_2.3_V6-step00016500.comfy.safetensors). Safetensors is the modern AI model format. It loads faster than the older ckpt format and cannot execute arbitrary code on load, which makes it the safer default. This model is mirrored across CivitAI, HuggingFace, and TensorFiles. CivArchive tracks every known copy by SHA256 hash, so the same file is reachable from any source that still has it online.
