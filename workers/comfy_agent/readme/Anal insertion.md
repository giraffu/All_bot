ltx2.3 - i2v 1.0
No audio , produces body horror sometimes. (and tail/sack?)
Works on it's own or merge at 0.8 + 0.4 with other nsfw loras for more motion/less body horror.

Works with strange kinks as well if prompted. (in reverse ?)

Use last frame only with no start frame for different effect.
Add other loras for more dynamic "transition".

Description
FAQ
What is Anal insertion (I2V)?
Anal insertion (I2V) is a concept LoRA designed for LTX Video-family checkpoints, published by blo01 on CivitAI in September 2025, now on version 3. It layers on top of any compatible LTX Video checkpoint. You load the checkpoint first, then apply this LoRA on top of it. It has attracted 3,509 downloads. The model is flagged NSFW on CivitAI and can produce explicit content.

How do I use Anal insertion (I2V)?
Triggers. This LoRA activates with the following trigger words: Anal insertion., being penetrated by the man's large p3nis, He helps to guide it in.. Include them in your positive prompt to pull the trained concept into the output. Without the trigger, the LoRA still has some effect, but it is usually much weaker.

Prompting. LTX Video uses natural-language sentences. LTX is notably prompt-sensitive and rewards longer, more detailed prompts than competitors. Motion-focused action verbs and specific descriptive language work better than short prompts. Users commonly employ external LLMs (ChatGPT, Grok) to enhance prompts or use multimodal vision models to analyze input images and generate video-appropriate descriptions. Add the trigger words (Anal insertion., being penetrated by the man's large p3nis, He helps to guide it in.) alongside your normal prompt.

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
This version ships as a 768 MB safetensors file (nsfw_anal_insertion_ltx23_v1.0.safetensors). Safetensors is the modern AI model format. It loads faster than the older ckpt format and cannot execute arbitrary code on load, which makes it the safer default. This model is mirrored across CivitAI and HuggingFace. CivArchive tracks every known copy by SHA256 hash, so the same file is reachable from any source that still has it online.