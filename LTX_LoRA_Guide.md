# LTX-2.3 工作流 LoRA 综合使用指南

本文档汇集了当前目录下 11 个针对 LTX-2.3 视频生成工作流的 LoRA 模型的使用说明与参考提示词。LTX 系列模型对提示词非常敏感，建议在生成时使用**详细、客观、机械性**的描述语言（如同你在指导摄像师或动作演员），避免使用抽象或诗意的词汇。

---

## 1. DR34ML4Y (全能多姿势综合 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/DR34ML4Y.md`
- **模型简介**：这是一个全能型的 NSFW LoRA，单模型即可支持多种姿势（如传教士、口交、双人口交、女上位、后入等）。
- **推荐参数**：建议不使用蒸馏（Distillation）模型，或者将蒸馏强度设置在 `0.25 - 0.35` 之间。
- **触发词与参考提示词**：
  - **传教士** (`m15510n4ry`): `m15510n4ry, 传教士体位的特写，女人平躺在白色床的边缘，男人在她张开的双腿之间。光线均匀，突出自然的肤色和纹理。`
  - **口交** (`bl0wj0b`): `bl0wj0b, 特写镜头，一个年轻女人正在给男人吹箫。她几乎全裸，手握阴茎根部引导动作。`
  - **双人口交** (`d0ubl3_bj`): `d0ubl3_bj, 特写镜头，两个女孩正在进行双人口交。电影感但带有偷窥视角的打光。`
  - **反向骑乘** (`c0wg1rl`): `c0wg1rl, 4k高清视频，侧面视角，一个年轻女孩双手放在背后，双腿分开呈反向骑乘姿势。男人从下方插入。`
  - **后入式** (`d0gg1e`): `d0gg1e, 4k高清视频，一个年轻女人趴在床上，臀部翘起，被男人从后方插入。她回头看向镜头。`

---

## 2. LTXdeepthroat (深喉/口交动作 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/LTXdeepthroat.md`
- **模型简介**：专用于生成深喉/口交内容的 LoRA。需要非常字面、具体的动作描述，对男性的躯干也必须明确描述（肤色、体毛等），否则会变成模糊的肉块。
- **推荐参数**：LoRA 强度 (Stage 1) `1.0`；(Stage 2) `0.85`；蒸馏 LoRA (Stage 2) `0.6`。
- **触发词**：`LTXdeepthroat`
- **动作词汇推荐**：`glans` (龟头), `shaft` (阴茎干), `base` (根部), `slides / glides` (女方控制滑动), `thrusts` (男方控制抽插)。
- **参考提示词**：
  - `LTXdeepthroat, 第一人称POV俯视视角。一个留着金色长发、皮肤白皙的女人。能看到男人裸露的躯干，有自然的皮肤纹理和淡淡的体毛。她的嘴唇紧紧包住阴茎（lips sealed around shaft，防止舌头乱动），缓慢向前滑向根部。她向后退开，闪闪发光的阴茎再次显露。固定镜头，柔和温暖的光线。`

---

## 3. Penial Praxis v4.0 (多姿势与画风 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/Penile Praxis.md`
- **模型简介**：综合性 LoRA，不仅支持各类动作（手淫、乳交、自交等），还新增了画风控制功能，且在男性对象上同样生效。
- **推荐参数**：搭配 Wan2GP 模型效果更好。
- **参考提示词**：
  - **画风控制**: `This video is in a cartoon style.` (卡通风格) / `This video is in an anime style.` (动漫风格) / `This video is in a realistic anime style.` (写实动漫风格)
  - **动作描述**:
    - 手交: `a nude woman kneeling in front of a man giving him a handjob.` (一个裸体女人跪在男人面前给他手交。)
    - 乳交: `A woman is giving a man a boobjob from the man's POV. The man's penis is between her breast.` (男方视角的乳交，阴茎夹在乳房之间。)
    - 自交: `a nude man performing autofellatio on himself.` (裸体男人正在给自己口交。)

---

## 4. Pussyjob / Grinding (外阴摩擦 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/Pussyjob.md`
- **模型简介**：用于生成外阴摩擦动作的 LoRA。
- **推荐参数**：I2V (图生视频) 权重 `0.4 - 0.8`（如果破坏原图可降低）；T2V (文生视频) 权重 `1.0`。
- **参考提示词**：
  - **正向**：尝试在提示词中描述画面里的所有视觉细节。加入 `loop video` (循环视频) 对部分场景有效。
  - **负向 (Negative)**：`close-up, her face is out of frame, dynamic angle, camera motion, handheld camera, transition, cut, undress` (特写，脸在画外，动态角度，运镜，手持摄像机，转场，剪辑，脱衣服)。

---

## 5. VBVR Reasoning V3 (逻辑推理与运动控制 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/Reasoning.md`
- **模型简介**：这不是一个具体的动作 LoRA，而是一个**优化运动规律和提示词遵循度**的工具。它减少了画面中无意义的漂移，让该动的地方动，不该动的地方保持静止。全年龄/非NSFW场景也可使用。
- **推荐参数**：推荐强度 `0.7 - 1.0`。若需极强提示词遵循可开到 `1.5 - 2.0`（但可能会掉帧）。在图生视频中将图像强度降至 `0.85` 可增强运动幅度。
- **参考提示词技巧**：
  - **原则**：描述起始状态、动作过程、结束状态。
  - **示例**：不要写“水倒出来”，而是写：`Water flows from the left container through the connecting tube into the right container until both levels are equal` (水从左侧容器通过连接管流向右侧容器，直到两侧水位齐平)。

---

## 6. Stomach bulge (腹部凸起细节 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/Stomach bulge.md`
- **模型简介**：专注刻画性行为中，女方腹部随男方抽插动作产生凸起形变的物理效果。
- **推荐参数**：LTX-2.3 推荐权重 `0.8 - 1.0`；Wan2.2 推荐权重 `0.6 - 0.8`。
- **支持场景词**：`fast`, `slow`, `from below`, `from behind`, `held in arms`, `missionary`, `pov`, `riding on top`, `lying down`, `side view`
- **参考提示词**：
  - `st0mach, she is getting fucked, missionary position, pov, stomach is bulging with each thrust. A man is thrusting his penis back and forth.` (st0mach触发词，传教士体位，POV视角，随着男人的每一次抽插，女人的腹部都会明显凸起。男人正在前后抽插。)

---

## 7. Paizuri / Titfuck (乳交专用 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/Titfuck.md`
- **模型简介**：专为 LTX-2.3 训练的乳交模型，兼容写实和二次元风格。
- **推荐参数**：作者推荐搭配 furry nsfw lora（权重 `1.0`）使用。如果画面出现故障闪烁，可以尝试加入蒸馏 LoRA 并将权重设为 `-0.4` 到 `0.5` 左右。
- **参考提示词技巧**：此 LoRA 极其依赖详细提示词，必须按照 LTX 的规范，一步步客观写出胸部和阴茎的互动、物理挤压感等。

---

## 8. sfbehind (后入姿势专用 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/sfbehind.md`
- **模型简介**：专攻背向镜头的性爱姿势，支持狗狗式 (`doggy`)、俯卧 (`prone`)、翘臀趴姿 (`top-down bottom-up`)。
- **推荐参数**：Stage 1 权重 `1.0`，Stage 2 权重 `0.85`。
- **触发词**：`sfbehind`
- **参考提示词技巧**：
  - 必须客观描述碰撞反馈，如：`her buttocks compress and ripple on contact` (她的臀部在接触时被挤压并产生波纹)。
  - **短抽插示例**: `He thrusts his hips forward in short rapid strokes, her buttocks compressing on impact` (他快速短促地向前挺动臀部，她的臀部在撞击下被挤压)。
  - **长抽插示例**: `He pulls his hips back, the glistening shaft reappearing, then drives forward. Her buttocks ripple from the impact.` (他将臀部向后拉，闪闪发光的阴茎再次显露，然后向前推进。她的臀部因撞击而泛起波纹)。

---

## 9. Anal insertion (肛交插入 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/t.md` (nsfw_anal_insertion)
- **模型简介**：专攻肛交插入的动作。偶尔会产生肢体崩坏（Body Horror）。
- **推荐参数**：推荐权重 `0.8`。为了更好的动作连贯性，可与其他 NSFW LoRA 混合使用（如 `0.8 + 0.4`）。
- **触发词**：`Anal insertion.`, `being penetrated by the man's large p3nis`, `He helps to guide it in.`
- **参考提示词**：
  - 将上述触发词结合常规提示词一起使用，多使用聚焦于动作的动词，例如：`Anal insertion. He helps to guide it in. (肛交插入，他帮助引导进入...)`，并配合详细的机位描述。

---

## 10. Synth Pussy (女性私处与胸部细节强化 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/Synth Pussy.md`
- **模型简介**：这是一个专门用于强化女性私处（阴道和肛门）以及胸部静态细节的 LoRA。由于它仅基于静态图像训练，不包含动作数据，因此非常适合作为打底细节，与其他动作 LoRA 搭配使用。
- **推荐参数**：推荐权重在 `0.6 - 0.9` 之间，建议从 `0.8` 开始测试。
- **触发词**：无特定触发词，加载即可生效。
- **参考提示词与使用技巧**：
  - **防漏点技巧**：由于数据集原因，该模型容易让乳头透过薄衣服显露。如果不想过度暴露胸部，请在提示词中明确使用厚重衣物，如 `thick jackets` (厚夹克) 或 `wool sweaters` (羊毛毛衣)，并避免提及薄衣物。
  - **毛发控制**：目前模型倾向于生成完全白虎（shaven）的细节，如果需要毛发，建议与其他带有毛发（hairy）特征的 LoRA 混合使用。
  - 正常描述你想要的机位、肤色和光影即可。

---

## 11. Penis Lora (男性阴茎生成与动作控制 LoRA)
- **文件参考**: `/home/hfy/APP/All_bot/workers/comfy_agent/readme/plora_Penis.md`
- **模型简介**：专注于男性阴茎生成与动作（手淫、口交等）的强化 LoRA。完全基于高分辨率纯视频数据集训练，大部分为割包皮状态，未针对疲软状态进行训练。
- **推荐参数**：推荐权重在 `0.6 - 0.9` 之间，建议从 `0.8` 开始测试。
- **触发词**：`PENISLORA`（必须使用，并建议放在提示词的最前面）
- **参考提示词与使用技巧**：
  - 指代阴茎时必须使用单词 `Penis`。
  - **静态展示**：`PENISLORA, the man's penis is exposed` (男人的阴茎暴露在外，无动作) / `Penis shown from the front` (从正面展示) / `penis shown from the side` (从侧面展示)。
  - **动作描述**：`the man strokes his penis` (男人正在手淫) / `the woman strokes the man's penis` (女人正在给男人手交)。
  - **其他场景**：包含少量 `Blow job` (口交) 和 `deepthroat` (深喉) 的标注数据；尝试生成射精可以使用 `cum shoots from the penis`（但由于数据已被清洗，可能效果有限）。
- **已知问题与局限**：
  - 在一些奇特视角下，龟头部分可能生成不佳，建议多次抽卡尝试（更换 Seed）。
  - 如果没有指定具体的抚摸或吸吮动作，阴茎在画面中可能会异常弹跳（super bouncy）。
  - 有可能导致画面中的胸部/乳头生成异常，或在裸体女性身上随机生成阴茎，建议遇到时配合其他特定控制 LoRA 来修复。
