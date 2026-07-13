LTX 2.3
A LoRA for generating from-behind sex (facing the camera) positions with LTX-2.3 video models. Supports doggy style, prone, and top-down bottom-up positions. Check out the training data if you need help with workflows. Also I have attached my image captioning system prompt when using I2V that should help with language.

Trigger Word
sfbehind

Recommended Settings
LoRA strength (Stage 1) 1.0

LoRA strength (Stage 2) 0.85

Distilled LoRA (Stage 2) 0.6

Prompting Tips
This LoRA responds best to literal, mechanical prompts. Describe body positions and motion like you're directing a scene. Avoid poetic or abstract language.

Do: "He thrusts his hips forward in short rapid strokes, her buttocks compressing on impact" Don't: "A mesmerizing rhythm of primal passion"

Position Names
Use these exact terms — the model was trained on them:

doggy — on hands and knees

prone — lying flat face-down

top-down bottom-up — face pressed into bed, hips raised, back arched

Thrust Patterns
Two distinct patterns the model learned:

Close thrusts (no shaft visible): "He thrusts in short, rapid strokes, his hips staying pressed close to her ass. Her buttocks compress on each impact."

Long strokes (shaft visible): "He pulls his hips back, the glistening shaft reappearing, then drives forward. Her buttocks ripple from the impact."

Who Is Moving?
Man active: "He thrusts his hips forward" / "He drives into her"

Woman active: "She pushes her hips back into him" / "She rocks back against him"

Don't describe both moving unless both actually are.

Getting Better Results
Describe the male body — skin tone, build, body hair, tattoos, muscle definition. Without this it renders as a vague blob.

Describe impact reactions — "her buttocks compress and ripple on contact, her body rocking forward from the force." This teaches the model to sync the bounce with the thrust.

Describe contact points — "his hips press flush against her ass" or "his hands grip her waist."

If her face is visible describe it literally — mouth open, eyes closed, brow furrowed. Don't interpret emotion.

If no shaft is visible don't mention it. Describe hip motion and body contact only.

Specify the camera angle — straight-down, three-quarter, eye-level, low angle.

Known Quirks
Male torso needs explicit description or it gets blobby.

Impact bounce can desync if not described in the prompt — always include "buttocks compress" or "body rocks forward" tied to the thrust.

Stage 2 LoRA strength at 1.0 degrades quality. Keep at 0.85.

