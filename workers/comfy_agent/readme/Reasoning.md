This was the first VBVR lora trained for LTX 2.3
Tip appreciated if you enjoy the work, these take a lot of time to create! https://ko-fi.com/misticrain69
V3 has been optimized for motion. Expect noticeably livelier, more dynamic movement compared to previous versions. I generated the example videos using the int8/fp8 distilled model using 8 steps in wan2gp. I can highly recommend LTX 2.3 Sulphur 2 base if you are using comfyui and if your using wan2gp use the Sulphur 2 base rank 768 lora https://huggingface.co/SulphurAI/Sulphur-2-base/tree/main
What changed in V3: Attention-only layers. The feedforward layers have been stripped, leaving only the attention weights. It seems like the prompt following and reasoning behavior most likely live in the attention layers, while the feedforward layers were potentially interfering with natural motion, likely by over-learning features like textures and style from the training data.
Better motion, smaller file size.
A LoRA that improves prompt following, temporal consistency, and motion "precision" for LTX 2.3. Reduces the floaty, drifty motion that LTX tends to add to scenes. Things that should move, move with purpose. Things that shouldn't move, move less. Also works on non-NSFW, non-Furry, realistic, animated etc. It responds well to detailed prompts.
In comfyui or wan2gp lowering image strength to 0.85 can improve motion in general if you want more motion
Feedback and A-B comparisons welcome. V2 and V1 was trained on 4800 videos.
Recommended to run at strength 1.0-0.7 but experiment to find what works best for your setup. If you want stronger prompt adherence try strength 1.5-2.0. I have noticed the only side effect I have gotten from a high strength is the video looking like its 16fps. I have not seen the choppiness issues on i2v unless the lora is cranked to 1.5-2.0 so it may be a t2v thing.
Prompting tips in non-nsfw terms so its less confusing just adapt it to nsfw:
Be specific and literal. Describe what happens, in what order, step by step.
Instead of "a ball bouncing around" → "A red ball moves to the right, bounces off the wall, and returns to the center"
Instead of "fluid pouring" → "Water flows from the left container through the connecting tube into the right container until both levels are equal"
Describe the starting state, the action, and the end state
The LoRA follows prompts more literally than base LTX — precise prompts will give much better results
How was it made?
v0.1 and v0.2 were trained on 360 videos from the VBVR (Very Big Video Reasoning) dataset synthetic task videos where every motion is precise and intentional. No concept bleed, no style change, just tighter control.
Based on the paper "A Very Big Video Reasoning Suite" which demonstrated this approach on Wan 2.2. I noticed that lora helped prompt following and temporal consistency a ton with wan so I am training this version for LTX.
What does it actually do?
Prompt following is more faithful — the model does more of what you asked instead of improvising
Motion is more deliberate and less erratic
Reduces random drift and wobble in scenes
Temporal consistency improved — actions follow logical sequences
What it doesn't do:
Doesn't change visual style
Doesn't add or remove capabilities LTX doesn't already have
Not a motion LoRA — stacks with motion LoRA's
Training details for v0.1 and v0.2 (if you give a shit)
Rank 32
360 VBVR synthetic videos at 512x512, 81 frames <------Alot less than 1 million but still a shitload to train on this is very slow to train locally.
LR 1e-4, adamw8bit
Training details for V1
Training videos were increased to 4800
Resolution is the same but frames were increased to 121
Every other setting the same as v0.1 and v0.2
More training data from the VBVR dataset was added to v1
Below is the new dataset I trained on's data composition if your curious
Tier 1 — Physics and Motion (3,400 samples)
Core generators at 300 each: G-11 (object reappearance) has a shape move off-screen in a direction and return along the same path — teaches trajectory and object persistence. G-25 (separate object spinning) is a shape that rotates in place then translates horizontally to a target position — multi-step motion sequencing. G-33 (visual jenga) is a stack of objects that get removed one by one from top to bottom — sequential extraction with implicit physics ordering. O-29 (ballcolor) is ball tracking tasks with color — motion following plus identity preservation. O-52 (traffic light) is discrete state transitions, lights switching on/off between green and gray — teaches the model that state changes are crisp, not gradual. O-75 (communicating vessels) is fluid equalizing between connected tubes based on pressure — continuous physics simulation over time. O-87 (fluid diffusion) is ink spreading in water — another continuous physical transformation but with expansion rather than equalization.
New additions at 250 each: G-35 (hit target after bounce) is a ball with an initial direction that bounces off walls following reflection laws to hit a target — pure trajectory prediction with physics constraints. O-30 (bookshelf) is book rearrangement on shelves — the specific task VBVR highlighted where their model beat Sora 2.
Multi-step transforms at 160 each: O-7 (shape color change) is a single transformation — shape changes from one color to another. O-8 (shape rotation) is a shape rotating by a specific angle. O-13 (outline then move) is two sequential steps: change a shape's outline style, then move it to a new position. O-14 (scale then outline) is also two steps: scale a shape up or down, then change its outline. These four together teach the model that instructions are ordered and each step completes before the next begins.
Tier 2 — Spatial and Reasoning (1,420 samples)
Proven generators at 100 each: G-13 (grid number sequence) is filling in number patterns on a grid. G-17 (grid avoid red block) is pathfinding on a grid while avoiding obstacles. G-31 (directed graph navigation) is finding the shortest path through a directed graph. G-41 (grid highest cost) is evaluating spatial values on a grid to find the optimal path. O-24 (domino chain) is a sequential cascade where dominoes fall until they hit a gap — teaches causal chains and stopping conditions. O-34 (dot to dot) is connecting numbered dots in sequence — ordered drawing. O-47 (sliding puzzle) is tile rearrangement under constraints, like a 15-puzzle. O-83 (planar warp) is warping a grid to align with a target quadrilateral — geometric transformation.
New reasoning diversity at 130 each: O-1 (color mixing) is RGB additive mixing where two light sources combine and the result fills a target zone — rule-based continuous process. O-33 (counting objects) is exactly what it sounds like — count things correctly. G-3 (stable sort) is arranging objects by a rule while preserving relative order. G-37 (symmetry random) is completing a pattern by mirroring across an axis. O-21 (construction blueprint) is fitting a correct puzzle piece into a gap in a structure. G-44 (BFS) is breadth-first search traversal of a graph — systematic layer-by-layer exploration.
The overall dataset is weighted roughly 70/30 toward physical motion and transformation tasks over abstract spatial reasoning, All of these are taken from the VBVR dataset I am not the creator of the dataset. I'm pretty new to lora training so if you have tips let me know.
REMEMBER its not X, its Y.
! If you post things in the gallery that violate the TOS I will block and report you. Don't do this shit.
For 18+ only. This is NOT to be used for any illegal or unethical purposes or on any real person or likeness. Don't be fucking sus.