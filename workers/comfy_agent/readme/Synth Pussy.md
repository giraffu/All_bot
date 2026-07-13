I'd appreciate some yellow Buzz if you can spare it - I'm trying to buy a 12k model here and anything helps toward that goal :)

************
As the name implies - This is detailed Pussy for LTX 2.3 .

Trained on 5k synthetic image dataset. I generated a wide range of angles, ethnicities, lighting conditions and poses.

This is purely a detail lora to get proper pussy and anus detail. No motion videos have been trained on. Any motion gained is pure luck.

That being said - it plays well with other existing motion loras found here on Civit. I see potential for training simple motion LoRAs to accompany this LoRA as this will do the detail heavy lifting without conflicting motions.

All example videos should have workflow embedded - if they won't load - there should be a single image uploaded as well that would have the WF embedded. It's nothing fancy but it'll give you a start.

PROS :

Good pussy and anus detail, learnt a couple of erotic poses as well.

No face modification. Works well T2V and i2v.

Even does realistic breasts.

CONS:

Too many breasts and nipples! through shirts! I realized too late that my dataset had too many full nudes in it and thus it very rapidly learnt to draw nipples and exposed breasts. By that time I was already too deep into training and didnt want to fix it.
I tried compensating by merging the 'best-breasts' lora found here on civit at a -0.1 value. It didnt fix the issue but it helped a little bit.
Avoid prompting thin clothing, prompt thick jackets and wool sweaters if you want to keep the ta-ta's hidden.

Only does fully shaven pussy right now. Majority of the dataset is clean like that. Might be able to blend it with some other hairy loras here for more fluff if you need.


Training details for those curious:

Trained with Musubi trainer - LR 0.00006 for 71,000 steps.
Some decent labia detail had emerged around 30k already but I wanted to push it longer so see if it would pick up on some of the subtler labia spreading details in the dataset.
At 30k I dropped the LR to 0.000045 and let it run . The LR was so low I could afford to let it run for a while without overfitting.

Images train much much faster than full videos and use much less VRAM. I could fit this into 24gb if I wanted to.

I'd suggest always doing a first run of image based training to establish details and then take over with your video motion dataset. This way you build a solid base understanding of the concept quickly allowing the video to come in and finish it off.

Description
FAQ
What is Synth Pussy - LTX 2.3?
Synth Pussy - LTX 2.3 is a concept LoRA designed for LTX Video-family checkpoints, published by QualityControl on CivitAI in April 2026. It layers on top of any compatible LTX Video checkpoint. You load the checkpoint first, then apply this LoRA on top of it. It has attracted 6,001 downloads. It's intended for nude, butt, vagina, nipples, and breasts content. The model is flagged NSFW on CivitAI and can produce explicit content.

How do I use Synth Pussy - LTX 2.3?
Triggers. No trigger words are listed on this version. The LoRA activates simply by being loaded into your generation. Check the author's description on this page for any tag-based activation hints that might still apply.

Prompting. LTX Video uses natural-language sentences. LTX is notably prompt-sensitive and rewards longer, more detailed prompts than competitors. Motion-focused action verbs and specific descriptive language work better than short prompts. Users commonly employ external LLMs (ChatGPT, Grok) to enhance prompts or use multimodal vision models to analyze input images and generate video-appropriate descriptions. Prompt as you normally would for this base model. The LoRA influences the output without needing specific trigger words.

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
This version ships as a 336 MB safetensors file (SynthPussy_01_rank32.safetensors). Safetensors is the modern AI model format. It loads faster than the older ckpt format and cannot execute arbitrary code on load, which makes it the safer default. This model is mirrored across CivitAI and HuggingFace. CivArchive tracks every known copy by SHA256 hash, so the same file is reachable from any source that still has it online.