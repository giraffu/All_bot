from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_T2V,
)
from src.prompt_optimizer.minimax_h3_prompt import (
    MINIMAX_H3_10EROS_NAUGHTYTIMES_SYSTEM,
    MINIMAX_H3_10EROS_NAUGHTYTIMES_USER,
    MINIMAX_H3_HMNSFW_SYSTEM,
    MINIMAX_H3_HMNSFW_USER,
)

PROMPT_OPTIMIZATION_COST = 1
PROMPT_OPTIMIZE_TASK_TYPE = "prompt_optimize"
LTX_VIDEO_V2_TASK_TYPE = "ltx_video_v2"
LTX_VIDEO_V2_FLF2V_TASK_TYPE = "ltx_video_v2_flf2v"
LTX_T2V_TASK_TYPE = "ltx_t2v"
LTX_T2V_IC_TASK_TYPE = "ltx_t2v_ic"


class PromptOptimizerRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PromptOptimizationTemplate:
    id: str
    version: int
    label: str
    description: str
    system_template: str
    user_template: str
    required_variables: tuple[str, ...]
    compatible_profile_refs: frozenset[str]
    active: bool = True

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(
            {
                "id": self.id,
                "version": self.version,
                "system_template": self.system_template,
                "user_template": self.user_template,
                "required_variables": self.required_variables,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PromptOptimizationProfile:
    id: str
    version: int
    supported_target_task_types: frozenset[str]
    required_media_roles: tuple[str, ...]
    optional_media_roles: tuple[str, ...]
    allowed_durations: frozenset[int]
    output_fields: tuple[str, ...]
    primary_field: str
    model_route: str
    allowed_template_refs: frozenset[str]
    default_template_ref: str
    max_input_characters: int = 2000
    max_output_characters: int = 2000
    active: bool = True

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


@dataclass(frozen=True, slots=True)
class ResolvedPromptOptimization:
    profile: PromptOptimizationProfile
    template: PromptOptimizationTemplate
    normalized_context: Mapping[str, Any]
    normalized_media: tuple[Mapping[str, str], ...]


_CINEMATIC_SYSTEM = """You compile concise English prompts for a target generation task.
Use attached media only as visual evidence. Preserve the user's intent and explicit constraints.
Never choose or recommend models, LoRAs, samplers, prices, resolutions, or workflows.
Return only JSON matching the supplied schema, without Markdown or analysis."""

_CINEMATIC_USER = """Target profile: {profile_ref}
Duration: {duration_seconds} seconds.
Use start_image exactly as the first frame{end_frame_clause}.
Write 4-8 short cinematic sentences: overall style and camera movement, environment and light,
then a Performance: section with natural body language, expression, pauses and clear actions.
Add Dialogue: only when the user's idea calls for it. Do not add unobserved characters.
Original idea: {original_prompt}"""

_TIMESTAMP_SYSTEM = """You compile motion-focused English scene scripts for a target generation task.
Use attached media only as visual evidence. Preserve the user's intent and explicit constraints.
Never choose or recommend models, LoRAs, samplers, prices, resolutions, or workflows.
Return only JSON matching the supplied schema, without Markdown or analysis."""

_TIMESTAMP_USER = """Target profile: {profile_ref}
Use start_image exactly as the first frame{end_frame_clause}.
Write concise timestamp blocks covering exactly {duration_seconds} seconds. Use four-second blocks,
with a shorter final block when needed. The first block anchors the visible starting pose; later
blocks focus on continuous movement and evolution. Keep the user's central action prominent.
Original idea: {original_prompt}"""

_SINGLE_IMAGE_CINEMATIC_SYSTEM = """You are an expert at creating short cinematic video prompts from a single attached reference image.

When the user attaches an image and asks for "one for this image" or similar, generate a response using this exact format and style:

Use the provided start image exactly as the first frame. [One-sentence description of the overall cinematic style and camera movement]. [Short description of the environment, lighting, and atmosphere].

Performance: [Detailed but concise performance notes for the main character(s), including body language, facial expressions, emotions, and specific actions].

[If dialogue is appropriate, add a Dialogue section with character names and delivery style.]

Keep the acting natural and cinematic. Small pauses, micro-expressions, realistic movement, and subtle environmental details. No exaggerated motion, no slapstick, no extra characters unless clearly visible in the image.

Keep the entire response to 4-8 sentences maximum. Focus on a simple, logical, and interesting motion evolution that flows naturally from the starting pose in the image. Use strong verbs and cinematic language."""

_SINGLE_IMAGE_CINEMATIC_USER = """One for this image.
Target profile: {profile_ref}
Video duration: {duration_seconds} seconds.
{media_frame_instructions}
Original request: {original_prompt}"""

_ADULT_CINEMATIC_SYSTEM = """你是一名专业的短篇电影化图生视频提示词编写专家。你的任务是结合参考图片、用户原始要求和视频时长，生成一份可直接用于 LTX 10Eros v1.4 图生视频的英文提示词。

你必须使用中文理解并执行全部规则，但最终生成的 positive_prompt 必须完全使用英文。不要输出中文解释、分析过程、修改建议、多个候选版本或 Markdown。

一、参考图片与首尾帧

必须将提供的 start_image 严格作为视频第一帧。start_image 是视觉事实，第一帧中的人物数量、人物身份、年龄特征、脸部、发型、身体结构、初始穿衣状态、姿势、空间位置、环境、构图和镜头方向必须与图片保持一致。

不要重新设计第一帧，不要虚构图片中不存在的人物，不要擅自替换、删除、融合或复制任何可见人物。

如果任务同时提供 end_image，则必须将 end_image 严格作为视频最终帧。描述一段从 start_image 自然发展到 end_image 的连续动作，确保人物数量、身份、身体方向、服装状态、姿势和空间关系能够合理过渡。不要生成与终帧冲突的中间事件，也不要在没有动作过程的情况下瞬间切换到终帧。

第一帧之后，允许人物通过连续、可见且符合身体力学的动作脱衣、改变姿势、靠近彼此、发生身体接触或进入更加露骨的性行为。任何衣物、姿势、镜头或身体状态变化都必须具有清晰的动作过程，禁止瞬间变化或无原因跳转。

二、默认成人 NSFW 方向

此任务默认用于成年人的 NSFW、色情和性爱图生视频。

只要参考图片中的人物可以明确判断为成年人，并且用户没有明确要求保持非色情内容，就应主动把普通、含蓄、简短或信息不足的用户构思扩展成明确、色情、具有强烈性张力的成人场景。

不要等待用户明确写出“露骨”“色情”或具体性行为。应根据参考图片中的人物数量、裸体或穿衣状态、姿势、视线、镜头角度、身体距离、空间关系、环境以及用户原始构思，选择一种最自然、最符合当前画面条件的成人情色发展方向。

可采用的方向包括但不限于：裸体展示、挑逗、自我展示、情色抚摸、揉捏、打屁股、自慰、口交、插入式性爱、骑乘、体位变化、多人配合或其他适合当前画面的成人性行为。

如果图片已经明确表现某种性行为，应直接延续并强化该行为，不要把它降级成普通亲密互动，也不要突然切换成无关的性行为。

如果图片表现的是成年人的裸体、内衣、床上姿势、挑逗性自拍或具有明显性暗示的构图，应主动把它发展成与当前姿势和环境自然衔接的情色表演。

如果图片只是普通成年人物，但用户没有明确要求非色情内容，可以在不增加额外人物、不破坏身份和场景连续性的前提下，逐步发展性张力、脱衣、身体展示、自慰或人物之间的情色接触。

只有当用户明确要求 SFW、纯剧情、非色情、保持衣物或禁止某类动作时，才降低色情强度，并严格遵守用户的明确限制。

三、输出结构

生成一份完整的英文视频提示词，并使用以下结构：

Use the provided start image exactly as the first frame. [用一句话描述电影化风格、镜头归属、POV、角度、构图以及一个简单明确的镜头运动。] [仅在相关时简要描述环境、灯光和氛围。]

Performance: [描述从图片可见初始姿势开始的一段清晰、连续、具体的动作发展。明确每个动作由谁执行、作用于谁，并描述肢体语言、视线、面部表情、情绪、手的位置、嘴的位置、身体接触、重心转移、停顿、身体反应和真实运动。]

[只有当对白能够实质性增强场景时，才添加 Dialogue: 或 Sexual Dialogue:。保留用户要求的语言、口音、准确措辞、语气和说话方式。]

[只有确实需要第二阶段动作、镜头复位、动作升级、体位变化或向终帧过渡时，才添加 Continued Performance:。]

最后使用一条简短句子强调自然表演、真实动作、身体连续性、声音以及需要避免的异常。

四、电影化动作规则

保持表演自然、明确且具有电影感。使用具体、有力、可以被视频模型表现的动作动词。

描述短暂停顿、呼吸变化、视线移动、微表情、头部倾斜、身体紧张或放松、手指动作、重心变化、身体回弹以及细微的环境运动。

每个动作必须自然承接上一个动作。角色不能在没有动作过程的情况下改变位置、姿势、服装或身体方向。

优先生成一条简单、符合逻辑、视觉上有趣的动作发展线。不要堆积大量互不相关的动作，不要在短视频中安排过多体位或场景变化。

镜头运动应保持简单且可执行，例如缓慢推进、轻微手持晃动、自拍式移动、轻微摇摄、短暂拉近面部或在动作升级后恢复原构图。不要同时使用多个复杂镜头运动。

必须明确镜头由谁持有，以及 POV 属于哪一名角色。第一人称 POV 场景中，不要错误描述镜头后方人物完整可见的身体或面部。

五、露骨内容的表达强度

不要淡化、净化或回避成人色情内容，也不要使用“亲密互动”“探索身体”“发生关系”等含糊委婉词替代必要的具体动作。

在有助于准确表达时，使用直接、明确的成年人体和性行为英文词汇。

必须具体描述：

- 性姿势以及人物之间的身体对位。
- 谁在触摸谁、谁在执行动作、动作作用于哪个身体部位。
- 手、嘴、舌头、手指、身体和性器官的位置及接触关系。
- 动作的方向、幅度、深度、节奏、力度和速度变化。
- 接触过程中身体、皮肤、胸部、臀部、肌肉和柔软组织的真实反应。
- 人物的眼神、面部表情、呼吸、呻吟、说话、紧张、兴奋和情绪变化。
- 在适合时描述皮肤接触声、湿润声、拍打声、床垫声、衣物摩擦声、喘息、呻吟和环境声音。

动作应该具有时间发展：从第一帧的初始姿势开始，逐步建立性张力，进入明确动作，再自然增加节奏、力度或情绪强度。

不要只描述一个静态色情姿势。提示词必须说明接下来实际发生什么，以及动作如何连续演进。

六、多人场景

对于露骨的多人场景，必须使用稳定的可见特征分别追踪每一名成年人，例如发色、发型、眼睛颜色、位置、服装或其他可靠的视觉特征。

必须明确每个动作的执行者和承受者，不能使用含糊的“她”“他们”导致角色混淆。

描述每个人的位置、身体朝向、手部动作、嘴部动作、视线、表情、节奏、反应以及他们之间如何协调。

不要让人物交换身份，不要把一个人的动作错误分配给另一个人，不要融合身体，不要生成重复人物，也不要让多人同时占据同一空间。

七、不同成人场景的编写要求

露骨口交或多人互动：

明确每一名成年参与者、各自位置、嘴部和手部动作、接触位置、动作节奏、深度变化、其他参与者的辅助动作、面部反应、眼神、呼吸、发声以及湿润接触声音。多人动作必须相互协调，并从图片中的初始位置自然开始。

插入式性行为：

明确具体体位、POV、身体对位、进入方向、动作节奏和强度、手部接触、身体反应和镜头运动。可以描述动作逐渐加快、加深、暂停、恢复、镜头拉近面部或在升级后恢复原角度，但不要安排过多体位切换。

单人裸体展示或自慰：

明确由谁控制镜头、镜头位于什么位置、身体如何展示、手部移动路径和动作节奏、挑逗表情、眼神交流、身体扭动、呼吸和兴奋程度的发展。只有用户要求或当前场景自然适合时，才描述高潮、体液、明确对白和相关声音。

情色抚摸、揉捏或打屁股：

明确是哪一方的手执行动作、准确的身体部位、抓握、揉捏、分开、抚摸或拍打方式。随后描述真实的皮肤移动、身体回弹、声音、喘息、表情和情绪反应。动作不能像机械重复，也不能造成身体变形。

脱衣、骑乘或体位变化：

描述衣物如何被拉开、解开、滑落或脱下，并描述手臂、腿部、身体平衡和重心的连续变化。人物靠近、跨坐、跪坐、翻身或改变体位时，必须说明腿和手如何移动、身体如何接触以及最终姿势如何形成，避免穿模和不可能的肢体移动。

八、对白和声音

只有当对白能够增强人物关系、色情氛围或动作表现时才添加对白。

用户指定对白时，应尽可能保留原句、语言、口音、称呼和情绪。不要擅自把外语对白翻译成英文。

对白格式示例：

Sexual Dialogue:
Female, breathless and aroused: "..."
Male, low and exerted: "..."

对白必须简短，不能占据提示词的大部分篇幅。

声音应与动作对应，例如呼吸、呻吟、亲吻、湿润接触、皮肤拍打、床垫移动、衣物摩擦或环境声音。不要加入与画面动作无关的声音，也不要堆积过多拟声词。

九、连续性与质量限制

不要生成身体结构变异、多余肢体、多余手指、身体融合、人物复制、肢体穿透、穿模、不合理裁切或突然改变人物身份。

不要生成没有动作过程的突然脱衣、瞬间位移、突然换姿势、突然改变镜头方向或突然出现新人物。

不要加入滑稽动作、闹剧式动作、夸张表演、无法实现的柔韧动作、机械重复、僵硬运动或违反人体关节结构的动作。

除非静态图片细节对于区分人物、保持身份或解释下一步动作是必要的，否则不要浪费篇幅完整复述图片。

不要推荐或讨论模型、LoRA、采样器、CFG、分辨率、价格、工作流、节点或生成参数。

十、长度和最终要求

最终英文提示词通常保持为 4～8 个信息充分的句子。为了多人动作、对白或第二阶段动作，可以使用较长的复合句，但必须保持清晰。

允许使用以下英文标签：

Performance:
Dialogue:
Sexual Dialogue:
Continued Performance:

最终只生成一份英文提示词。不要生成多个方案，不要解释为什么这样写，不要描述你的分析过程。

根据参考图片、用户原始要求和视频时长，选择一条最自然、最明确、最色情、最容易被视频模型连续表现的成人动作发展线。"""

_ADULT_CINEMATIC_USER = """目标 Profile：{profile_ref}
视频时长：{duration_seconds} 秒
媒体角色：
{media_frame_instructions}

用户原始要求：
{original_prompt}

请根据参考图片和以上要求生成最终英文 positive_prompt。"""

_T2V_REFERENCE_SECTION = """一、角色与场景参考

此任务是文生视频，参考图片不是视频首帧或终帧。绝对不要要求视频复制任何参考图的构图或姿势。

当提供 reference_character_1 和 reference_character_2 时，它们分别是两名成年角色的身份事实。必须保留各自可见的脸部、发型、身体特征和稳定身份，使用可靠特征分别追踪角色，禁止交换、融合、复制或凭空增加人物。

scene_background 只定义场景、空间布局、光线、氛围和可见环境。人物必须自然地处于该场景中，但不要求复刻背景图中的人物、姿势或拍摄时刻。

纯文生视频没有参考图片时，只根据用户原始要求建立角色和场景，不要声称看到了不存在的视觉事实。

所有人物、服装、姿势、接触和镜头变化都必须经过连续、可见且符合身体力学的动作发展，禁止瞬间变化或无原因跳转。

"""

_T2V_ADULT_CINEMATIC_SYSTEM = (
    (
        _ADULT_CINEMATIC_SYSTEM.split("一、参考图片与首尾帧", 1)[0]
        + _T2V_REFERENCE_SECTION
        + "二、默认成人 NSFW 方向"
        + _ADULT_CINEMATIC_SYSTEM.split("二、默认成人 NSFW 方向", 1)[1]
    )
    .replace(
        "Use the provided start image exactly as the first frame. [用一句话描述电影化风格、镜头归属、POV、角度、构图以及一个简单明确的镜头运动。] [仅在相关时简要描述环境、灯光和氛围。]",
        "[用一句话描述电影化风格、镜头归属、POV、角度、构图以及一个简单明确的镜头运动。] [仅在相关时简要描述环境、灯光和氛围。]",
    )
    .replace("从图片可见初始姿势开始", "从用户设定的初始状态开始")
    .replace("从第一帧的初始姿势开始", "从用户设定的初始状态开始")
)

_T2V_ADULT_CINEMATIC_USER = """目标 Profile：{profile_ref}
视频时长：{duration_seconds} 秒
参考媒体语义：
{media_frame_instructions}

用户原始要求：
{original_prompt}

请生成最终英文 positive_prompt。不要把角色参考图或背景参考图描述为视频首帧。"""

_I2V_PROFILE_REFS = frozenset({"ltx_eros_v14_i2v@1", "ltx_eros_v14_flf2v@1"})
_T2V_PROFILE_REFS = frozenset({"ltx_eros_t2v@1", "ltx_eros_t2v_ic_msr@1"})
_MINIMAX_H3_V1_PROFILE_REFS = frozenset(
    {
        "minimax_h3_t2v_prompt@1",
        "minimax_h3_i2v_prompt@1",
        "minimax_h3_flf2v_prompt@1",
    }
)
_MINIMAX_H3_V2_PROFILE_REFS = frozenset(
    {
        "minimax_h3_t2v_prompt@2",
        "minimax_h3_i2v_prompt@2",
        "minimax_h3_flf2v_prompt@2",
    }
)

_TEMPLATES: Mapping[str, PromptOptimizationTemplate] = MappingProxyType(
    {
        "ltx_scene_script_cinematic@1": PromptOptimizationTemplate(
            id="ltx_scene_script_cinematic",
            version=1,
            label="电影场景脚本",
            description="自然表演、镜头和环境变化",
            system_template=_CINEMATIC_SYSTEM,
            user_template=_CINEMATIC_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "end_frame_clause",
                "original_prompt",
            ),
            compatible_profile_refs=_I2V_PROFILE_REFS,
            active=False,
        ),
        "ltx_timestamp_motion@1": PromptOptimizationTemplate(
            id="ltx_timestamp_motion",
            version=1,
            label="分段动作脚本",
            description="按时间段描述连续动作演进",
            system_template=_TIMESTAMP_SYSTEM,
            user_template=_TIMESTAMP_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "end_frame_clause",
                "original_prompt",
            ),
            compatible_profile_refs=_I2V_PROFILE_REFS,
            active=False,
        ),
        "ltx_scene_script_cinematic@2": PromptOptimizationTemplate(
            id="ltx_scene_script_cinematic",
            version=2,
            label="图生视频场景提示词",
            description="自然、电影化且从首帧连续演进的表演与动作",
            system_template=_SINGLE_IMAGE_CINEMATIC_SYSTEM,
            user_template=_SINGLE_IMAGE_CINEMATIC_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "media_frame_instructions",
                "original_prompt",
            ),
            compatible_profile_refs=_I2V_PROFILE_REFS,
            active=False,
        ),
        "ltx_scene_script_cinematic@3": PromptOptimizationTemplate(
            id="ltx_scene_script_cinematic",
            version=3,
            label="成人电影化提示词",
            description="默认增强成人 NSFW 动作、镜头与多人连续性",
            system_template=_ADULT_CINEMATIC_SYSTEM,
            user_template=_ADULT_CINEMATIC_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "media_frame_instructions",
                "original_prompt",
            ),
            compatible_profile_refs=_I2V_PROFILE_REFS,
        ),
        "ltx_scene_script_cinematic@4": PromptOptimizationTemplate(
            id="ltx_scene_script_cinematic",
            version=4,
            label="成人文生视频提示词",
            description="10Eros 成人场景、双角色身份与背景连续性",
            system_template=_T2V_ADULT_CINEMATIC_SYSTEM,
            user_template=_T2V_ADULT_CINEMATIC_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "media_frame_instructions",
                "original_prompt",
            ),
            compatible_profile_refs=_T2V_PROFILE_REFS,
        ),
        "minimax_h3_hmnsfw@1": PromptOptimizationTemplate(
            id="minimax_h3_hmnsfw",
            version=1,
            label="高级图生视频pro",
            description="MiniMax H3 的 200–270 词 HMNSFW 提示词",
            system_template=MINIMAX_H3_HMNSFW_SYSTEM,
            user_template=MINIMAX_H3_HMNSFW_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "media_frame_instructions",
                "original_prompt",
            ),
            compatible_profile_refs=_MINIMAX_H3_V1_PROFILE_REFS,
            active=False,
        ),
        "minimax_h3_10eros_naughtytimes@1": PromptOptimizationTemplate(
            id="minimax_h3_10eros_naughtytimes",
            version=1,
            label="高级图生视频pro",
            description="10Eros Beta2 + LightX2V 8-step + NaughtyTimes v2 固定栈提示词",
            system_template=MINIMAX_H3_10EROS_NAUGHTYTIMES_SYSTEM,
            user_template=MINIMAX_H3_10EROS_NAUGHTYTIMES_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "media_frame_instructions",
                "original_prompt",
            ),
            compatible_profile_refs=_MINIMAX_H3_V2_PROFILE_REFS,
        ),
    }
)

_I2V_ALLOWED_TEMPLATE_REFS = frozenset(
    {
        "ltx_scene_script_cinematic@1",
        "ltx_timestamp_motion@1",
        "ltx_scene_script_cinematic@2",
        "ltx_scene_script_cinematic@3",
    }
)
_PROFILES: Mapping[str, PromptOptimizationProfile] = MappingProxyType(
    {
        "ltx_eros_v14_i2v@1": PromptOptimizationProfile(
            id="ltx_eros_v14_i2v",
            version=1,
            supported_target_task_types=frozenset({LTX_VIDEO_V2_TASK_TYPE}),
            required_media_roles=("start_image",),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15, 20}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=_I2V_ALLOWED_TEMPLATE_REFS,
            default_template_ref="ltx_scene_script_cinematic@3",
        ),
        "ltx_eros_v14_flf2v@1": PromptOptimizationProfile(
            id="ltx_eros_v14_flf2v",
            version=1,
            supported_target_task_types=frozenset({LTX_VIDEO_V2_TASK_TYPE}),
            required_media_roles=("start_image", "end_image"),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15, 20}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=_I2V_ALLOWED_TEMPLATE_REFS,
            default_template_ref="ltx_scene_script_cinematic@3",
        ),
        "ltx_eros_t2v@1": PromptOptimizationProfile(
            id="ltx_eros_t2v",
            version=1,
            supported_target_task_types=frozenset({LTX_T2V_TASK_TYPE}),
            required_media_roles=(),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15, 20}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=frozenset({"ltx_scene_script_cinematic@4"}),
            default_template_ref="ltx_scene_script_cinematic@4",
        ),
        "ltx_eros_t2v_ic_msr@1": PromptOptimizationProfile(
            id="ltx_eros_t2v_ic_msr",
            version=1,
            supported_target_task_types=frozenset({LTX_T2V_IC_TASK_TYPE}),
            required_media_roles=(
                "reference_character_1",
                "reference_character_2",
                "scene_background",
            ),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15, 20}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=frozenset({"ltx_scene_script_cinematic@4"}),
            default_template_ref="ltx_scene_script_cinematic@4",
        ),
        "minimax_h3_t2v_prompt@1": PromptOptimizationProfile(
            id="minimax_h3_t2v_prompt",
            version=1,
            supported_target_task_types=frozenset({MINIMAX_H3_T2V}),
            required_media_roles=(),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=frozenset({"minimax_h3_hmnsfw@1"}),
            default_template_ref="minimax_h3_hmnsfw@1",
            max_output_characters=3000,
            active=False,
        ),
        "minimax_h3_i2v_prompt@1": PromptOptimizationProfile(
            id="minimax_h3_i2v_prompt",
            version=1,
            supported_target_task_types=frozenset({MINIMAX_H3_I2V}),
            required_media_roles=("start_image",),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=frozenset({"minimax_h3_hmnsfw@1"}),
            default_template_ref="minimax_h3_hmnsfw@1",
            max_output_characters=3000,
            active=False,
        ),
        "minimax_h3_flf2v_prompt@1": PromptOptimizationProfile(
            id="minimax_h3_flf2v_prompt",
            version=1,
            supported_target_task_types=frozenset({MINIMAX_H3_FLF2V}),
            required_media_roles=("start_image", "end_image"),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=frozenset({"minimax_h3_hmnsfw@1"}),
            default_template_ref="minimax_h3_hmnsfw@1",
            max_output_characters=3000,
            active=False,
        ),
        "minimax_h3_t2v_prompt@2": PromptOptimizationProfile(
            id="minimax_h3_t2v_prompt",
            version=2,
            supported_target_task_types=frozenset({MINIMAX_H3_T2V}),
            required_media_roles=(),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=frozenset({"minimax_h3_10eros_naughtytimes@1"}),
            default_template_ref="minimax_h3_10eros_naughtytimes@1",
            max_output_characters=3000,
        ),
        "minimax_h3_i2v_prompt@2": PromptOptimizationProfile(
            id="minimax_h3_i2v_prompt",
            version=2,
            supported_target_task_types=frozenset({MINIMAX_H3_I2V}),
            required_media_roles=("start_image",),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=frozenset({"minimax_h3_10eros_naughtytimes@1"}),
            default_template_ref="minimax_h3_10eros_naughtytimes@1",
            max_output_characters=3000,
        ),
        "minimax_h3_flf2v_prompt@2": PromptOptimizationProfile(
            id="minimax_h3_flf2v_prompt",
            version=2,
            supported_target_task_types=frozenset({MINIMAX_H3_FLF2V}),
            required_media_roles=("start_image", "end_image"),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=frozenset({"minimax_h3_10eros_naughtytimes@1"}),
            default_template_ref="minimax_h3_10eros_naughtytimes@1",
            max_output_characters=3000,
        ),
    }
)


def _template_ref(template_id: str, version: int) -> str:
    return f"{str(template_id).strip()}@{int(version)}"


def _normalize_media(media: list[dict[str, Any]]) -> tuple[Mapping[str, str], ...]:
    if not isinstance(media, list):
        raise PromptOptimizerRegistryError("media must be an array")
    normalized: list[Mapping[str, str]] = []
    seen: set[str] = set()
    for item in media:
        if not isinstance(item, dict):
            raise PromptOptimizerRegistryError("media entries must be objects")
        if set(item) != {"role", "object_key"}:
            raise PromptOptimizerRegistryError("media entries contain unknown fields")
        role = str(item.get("role") or "").strip()
        object_key = str(item.get("object_key") or "").strip()
        if not role or not object_key or role in seen:
            raise PromptOptimizerRegistryError(
                "media roles and object keys must be unique"
            )
        seen.add(role)
        normalized.append(MappingProxyType({"role": role, "object_key": object_key}))
    return tuple(normalized)


def _resolve_profile(
    target_task_type: str,
    media: tuple[Mapping[str, str], ...],
) -> PromptOptimizationProfile:
    roles = tuple(item["role"] for item in media)
    profile_ref = ""
    if target_task_type == LTX_VIDEO_V2_TASK_TYPE:
        profile_ref = (
            "ltx_eros_v14_flf2v@1"
            if roles == ("start_image", "end_image")
            else "ltx_eros_v14_i2v@1"
            if roles == ("start_image",)
            else ""
        )
    elif target_task_type == LTX_T2V_TASK_TYPE and not roles:
        profile_ref = "ltx_eros_t2v@1"
    elif target_task_type == LTX_T2V_IC_TASK_TYPE and roles == (
        "reference_character_1",
        "reference_character_2",
        "scene_background",
    ):
        profile_ref = "ltx_eros_t2v_ic_msr@1"
    elif target_task_type == MINIMAX_H3_T2V and not roles:
        profile_ref = "minimax_h3_t2v_prompt@2"
    elif target_task_type == MINIMAX_H3_I2V and roles == ("start_image",):
        profile_ref = "minimax_h3_i2v_prompt@2"
    elif target_task_type == MINIMAX_H3_FLF2V and roles == (
        "start_image",
        "end_image",
    ):
        profile_ref = "minimax_h3_flf2v_prompt@2"
    profile = _PROFILES.get(profile_ref)
    if (
        profile is None
        or not profile.active
        or target_task_type not in profile.supported_target_task_types
    ):
        raise PromptOptimizerRegistryError("unsupported target task or media contract")
    return profile


def _normalize_context(
    profile: PromptOptimizationProfile,
    context: dict[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(context, dict) or set(context) != {"duration_seconds"}:
        raise PromptOptimizerRegistryError("context must contain only duration_seconds")
    try:
        duration = int(context["duration_seconds"])
    except (TypeError, ValueError) as exc:
        raise PromptOptimizerRegistryError(
            "duration_seconds must be an integer"
        ) from exc
    if duration not in profile.allowed_durations:
        raise PromptOptimizerRegistryError("unsupported duration_seconds")
    return MappingProxyType({"duration_seconds": duration})


def resolve_prompt_optimization(
    *,
    target_task_type: str,
    template_id: str,
    template_version: int,
    media: list[dict[str, Any]],
    context: dict[str, Any],
) -> ResolvedPromptOptimization:
    normalized_media = _normalize_media(media)
    profile = _resolve_profile(str(target_task_type).strip(), normalized_media)
    template = _TEMPLATES.get(_template_ref(template_id, template_version))
    if (
        template is None
        or not template.active
        or template.ref not in profile.allowed_template_refs
        or profile.ref not in template.compatible_profile_refs
    ):
        raise PromptOptimizerRegistryError("unknown or incompatible prompt template")
    return ResolvedPromptOptimization(
        profile=profile,
        template=template,
        normalized_context=_normalize_context(profile, context),
        normalized_media=normalized_media,
    )


def get_prompt_optimizer_capability(target_task_type: str) -> dict[str, Any]:
    target_task_type = str(target_task_type).strip()
    profiles = [
        profile
        for profile in _PROFILES.values()
        if profile.active and target_task_type in profile.supported_target_task_types
    ]
    if not profiles:
        raise PromptOptimizerRegistryError("unsupported target task type")
    template_refs = set.intersection(
        *(set(profile.allowed_template_refs) for profile in profiles)
    )
    default_ref = profiles[0].default_template_ref
    templates = [
        template
        for ref, template in _TEMPLATES.items()
        if ref in template_refs and template.active
    ]
    templates.sort(key=lambda item: (item.ref != default_ref, item.id, item.version))
    stream_fields = set.intersection(
        *(set(profile.output_fields) for profile in profiles)
    )
    required_roles = set.intersection(
        *(set(profile.required_media_roles) for profile in profiles)
    )
    all_roles = set().union(
        *(
            set(profile.required_media_roles) | set(profile.optional_media_roles)
            for profile in profiles
        )
    )
    ordered_roles = [
        "start_image",
        "end_image",
        "reference_character_1",
        "reference_character_2",
        "scene_background",
    ]
    return {
        "target_task_type": target_task_type,
        "cost": PROMPT_OPTIMIZATION_COST,
        "media_contract": {
            "required": [role for role in ordered_roles if role in required_roles],
            "optional": [
                role for role in ordered_roles if role in all_roles - required_roles
            ],
        },
        "text_stream": {
            "enabled": True,
            "schema_version": "allbot.text_stream.v1",
            "events": ["text_snapshot", "text_delta"],
            "fields": sorted(stream_fields),
        },
        "templates": [
            {
                "id": template.id,
                "version": template.version,
                "label": template.label,
                "description": template.description,
                "is_default": template.ref == default_ref,
            }
            for template in templates
        ],
    }


def get_profile_by_ref(profile_ref: str) -> PromptOptimizationProfile:
    profile = _PROFILES.get(profile_ref)
    if profile is None:
        raise PromptOptimizerRegistryError("unknown prompt profile")
    return profile


def get_template_by_ref(template_ref: str) -> PromptOptimizationTemplate:
    template = _TEMPLATES.get(template_ref)
    if template is None:
        raise PromptOptimizerRegistryError("unknown prompt template")
    return template


def render_prompt_messages(
    *,
    profile: PromptOptimizationProfile,
    template: PromptOptimizationTemplate,
    prompt: str,
    context: Mapping[str, Any],
) -> tuple[str, str]:
    variables = build_prompt_variables(profile=profile, prompt=prompt, context=context)
    missing = set(template.required_variables) - set(variables)
    if missing:
        raise PromptOptimizerRegistryError("template variables are unavailable")
    return (
        template.system_template.format_map(variables),
        template.user_template.format_map(variables),
    )


def build_prompt_variables(
    *, profile: PromptOptimizationProfile, prompt: str, context: Mapping[str, Any]
) -> dict[str, Any]:
    if profile.ref in {"minimax_h3_t2v_prompt@1", "minimax_h3_t2v_prompt@2"}:
        media_frame_instructions = (
            "No images are attached. This is text-to-video. Use only the original "
            "request and do not claim that a frame was observed."
        )
    elif profile.ref in {"minimax_h3_i2v_prompt@1", "minimax_h3_i2v_prompt@2"}:
        media_frame_instructions = (
            "Image 1 is start_image and is the exact first frame and visual fact."
        )
    elif profile.ref in {"minimax_h3_flf2v_prompt@1", "minimax_h3_flf2v_prompt@2"}:
        media_frame_instructions = (
            "Image 1 is start_image and is the exact first frame.\n"
            "Image 2 is end_image and is the exact final frame. Describe a continuous transition."
        )
    elif profile.ref == "ltx_eros_t2v@1":
        media_frame_instructions = (
            "No reference images are provided. Create the characters and scene only from "
            "the user's request."
        )
    elif profile.ref == "ltx_eros_t2v_ic_msr@1":
        media_frame_instructions = (
            "Image 1 is reference_character_1 and defines the first adult character's identity.\n"
            "Image 2 is reference_character_2 and defines the second adult character's identity.\n"
            "Image 3 is scene_background and defines only the setting, layout and lighting.\n"
            "These images are identity and environment references, not video frames."
        )
    else:
        media_frame_instructions = (
            "Image 1 is start_image and must be used exactly as the first frame.\n"
            "Image 2 is end_image and must be used exactly as the final frame."
            if "end_image" in profile.required_media_roles
            else "Image 1 is start_image and must be used exactly as the first frame."
        )
    return {
        "profile_ref": profile.ref,
        "duration_seconds": context["duration_seconds"],
        "end_frame_clause": (
            ", and use end_image exactly as the final frame"
            if "end_image" in profile.required_media_roles
            else ""
        ),
        "media_frame_instructions": media_frame_instructions,
        "addon_summary": "Fixed 10Eros-Max Beta2, LightX2V 8-step, and NaughtyTimes v2 stack; no user-selectable add-ons.",
        "addon_rules": "Do not output model names, LoRA names, strengths, or trigger tokens.",
        "breasts_vocabulary_rule": (
            "nipples and areoles require textual or visual evidence; areolas is forbidden."
        ),
        "original_prompt": str(prompt).strip(),
    }


def build_output_json_schema(profile: PromptOptimizationProfile) -> dict[str, Any]:
    field_properties = {
        field: {
            "type": "string",
            "minLength": 1,
            "maxLength": profile.max_output_characters,
        }
        for field in profile.output_fields
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["optimized_fields", "warnings"],
        "properties": {
            "optimized_fields": {
                "type": "object",
                "additionalProperties": False,
                "required": list(profile.output_fields),
                "properties": field_properties,
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string", "maxLength": 500},
                "maxItems": 8,
            },
        },
    }
