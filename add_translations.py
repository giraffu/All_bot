import json
import os

zh_path = 'shared/locales/zh.json'
en_path = 'shared/locales/en.json'

with open(zh_path, 'r', encoding='utf-8') as f:
    zh = json.load(f)

with open(en_path, 'r', encoding='utf-8') as f:
    en = json.load(f)

zh['task'] = {
    "img2img": "🎨 懒人/自由P图",
    "img2img_lora": "🎨 图生图 (附加模型)",
    "i2i_pro": "🌟 幻想换脸",
    "face_swap": "🎭 人脸替换",
    "video_insert": "🎬 视频插入",
    "video_edit": "🎬 视频编辑 (通用)",
    "face_video": "🎬 视频换脸",
    "ltx_video": "🎬 高级图生视频",
    "t2i_pornmaster_turbo": "🎨 文本生图",
    "custom_video": "🎬 自定义图生视频",
    "video_lora": "🎬 图生视频(附加模型)",
    "mode_edit": "自由P图",
    "mode_i2i_pro": "幻想换脸",
    "mode_img2img_lora": "图生图(附加模型)",
    "mode_undress": "快速脱衣",
    "mode_masturbation": "快速自慰",
    "mode_faceswap_step1": "快速换脸",
    "mode_faceswap_step2": "快速换脸",
    "mode_face_video_step1": "视频换脸",
    "mode_face_video_step2": "视频换脸",
    "mode_random_faceswap": "随机换脸",
    "mode_penetration_step1": "快速抽插",
    "mode_penetration_step2": "快速抽插",
    "mode_perfect_video_insert": "动图传教士",
    "mode_doggy_style": "动图后入",
    "mode_blowjob": "口交黑人",
    "mode_undress_tongue": "脱衣吐舌",
    "mode_closeup_blowjob": "特写口交",
    "mode_custom_video": "自定义图生视频",
    "mode_ltx_video": "高级图生视频",
    "mode_video_lora": "图生视频(附加模型)",
    "mode_template_contribute": "模板共建",
    "mode_none": "无模式"
}

en['task'] = {
    "img2img": "🎨 Custom Edit",
    "img2img_lora": "🎨 Img2Img (Addon)",
    "i2i_pro": "🌟 Pro Face Swap",
    "face_swap": "🎭 Face Swap",
    "video_insert": "🎬 Video Insert",
    "video_edit": "🎬 Video Edit",
    "face_video": "🎬 Video Face Swap",
    "ltx_video": "🎬 High-Res Video",
    "t2i_pornmaster_turbo": "🎨 Text2Img",
    "custom_video": "🎬 Custom Img2Video",
    "video_lora": "🎬 Img2Video (Addon)",
    "mode_edit": "Custom Edit",
    "mode_i2i_pro": "Pro Face Swap",
    "mode_img2img_lora": "Img2Img (Addon)",
    "mode_undress": "Fast Undress",
    "mode_masturbation": "Fast Masturbation",
    "mode_faceswap_step1": "Fast Face Swap",
    "mode_faceswap_step2": "Fast Face Swap",
    "mode_face_video_step1": "Video Face Swap",
    "mode_face_video_step2": "Video Face Swap",
    "mode_random_faceswap": "Random Face Swap",
    "mode_penetration_step1": "Fast Penetration",
    "mode_penetration_step2": "Fast Penetration",
    "mode_perfect_video_insert": "Perfect Video Insert",
    "mode_doggy_style": "Doggy Style",
    "mode_blowjob": "Blowjob",
    "mode_undress_tongue": "Undress Tongue",
    "mode_closeup_blowjob": "Closeup Blowjob",
    "mode_custom_video": "Custom Img2Video",
    "mode_ltx_video": "High-Res Video",
    "mode_video_lora": "Img2Video (Addon)",
    "mode_template_contribute": "Template Contribute",
    "mode_none": "No Mode"
}

en['app']['credits'] = "Credits"
zh['app']['credits'] = "灵石"

with open(zh_path, 'w', encoding='utf-8') as f:
    json.dump(zh, f, ensure_ascii=False, indent=2)

with open(en_path, 'w', encoding='utf-8') as f:
    json.dump(en, f, ensure_ascii=False, indent=2)

print("Translations added successfully.")
