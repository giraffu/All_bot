from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Iterable

from .prompt_vectors import (
    PromptTokenAliasRule,
    PromptTokenCustomTermRule,
    _valid_manual_prompt_token,
    normalize_prompt_token_alias_value,
    split_prompt_token_aliases,
)


PROMPT_TOKEN_RULE_SEED_BATCH_PREFIX = "seed-v1-categorized-basis"
PROMPT_TOKEN_RULE_OBSERVED_CUSTOM_LIMIT = 0
PROMPT_TOKEN_RULE_MIN_OBSERVED_PROMPT_COUNT = 20


TOKEN_CATEGORY_LABELS = {
    "preservation": "保持口径",
    "person": "人物主体",
    "body_part": "身体部分",
    "adult_anatomy": "身体部分",
    "adult_theme": "成人主题",
    "adult_action": "动作姿势",
    "pose_action": "动作姿势",
    "appearance": "外观特征",
    "clothing": "服饰配件",
    "expression": "表情情绪",
    "scene": "场景",
    "camera": "镜头构图",
    "style_quality": "风格质量",
    "observed": "观测高频词",
}

TOKEN_SUBCATEGORY_LABELS = {
    "identity": "主体身份",
    "people_count": "人数",
    "gender": "性别",
    "ethnicity": "族裔",
    "ethnicity_country": "族裔国别",
    "age": "年龄",
    "age_gender": "年龄性别",
    "ethnicity_age_gender": "族裔年龄性别",
    "numeric_age": "数字年龄",
    "relationship": "关系角色",
    "expression": "表情",
    "face": "面部",
    "hair": "头发",
    "chest": "胸部",
    "genital": "生殖器",
    "anus": "肛门",
    "fluid": "体液",
    "skin": "皮肤",
    "body_shape": "体型",
    "makeup": "妆容",
    "limb": "四肢",
    "adult_device": "器具道具",
    "adult_behavior": "成人行为",
    "sexual_behavior": "性行为",
    "nudity_change": "裸露变化",
    "nudity": "裸露",
    "adult_topic": "成人主题",
    "role": "关系角色",
    "humiliation": "羞辱/贬称",
    "fetish": "癖好",
    "pose": "姿势",
    "motion": "动作",
    "camera_angle": "角度",
    "shot": "景别",
    "frame_space": "画面空间",
    "lighting": "光影",
    "quality": "质量",
    "garment": "衣物",
    "color_garment": "颜色服饰",
    "garment_state": "衣物状态",
    "garment_material": "材质",
    "clothing_change": "服饰变化",
    "accessory": "配件",
    "place": "地点",
    "background": "背景",
    "background_preserve": "背景保持",
    "edit_intent": "编辑口径",
    "independent": "独立词",
}


@dataclass(frozen=True)
class TokenRuleSeed:
    term: str
    category_key: str
    subcategory_key: str = ""
    notes: str = ""


@dataclass(frozen=True)
class AliasRuleSeed:
    representative: str
    aliases: tuple[str, ...]
    category_key: str
    subcategory_key: str = ""


def _terms(category_key: str, subcategory_key: str, values: str) -> tuple[TokenRuleSeed, ...]:
    return tuple(
        TokenRuleSeed(term=value, category_key=category_key, subcategory_key=subcategory_key)
        for value in split_prompt_token_aliases(values)
    )


BASE_CUSTOM_TERM_SEEDS: tuple[TokenRuleSeed, ...] = (
    *_terms("preservation", "edit_intent", "保持, 不变, 一致, 完全一致, 保持一致, 保持不变, 保持一样, 原图, 参考图"),
    *_terms("preservation", "background_preserve", "原图背景, 背景不变, 保持背景"),
    *_terms("person", "identity", "人物, 角色, 主体, 模特, 真人"),
    *_terms("person", "gender", "女性, 女人, 男性, 男人"),
    *_terms("person", "people_count", "单人, 一人, 一位, 单男, 单女, 双人, 两人, 俩人, 多人, 三人, 四人, 五人"),
    *_terms("person", "ethnicity_country", "亚洲人, 东亚人, 黑人, 白人, 中国人, 日本人, 韩国人, 台湾, 台湾人, 欧美人, 非洲人"),
    *_terms("person", "age", "男孩, 女孩, 小男孩, 小女孩, 少年, 少女, 儿童, 孩子, 未成年, 小学生, 初中生, 中学生, 高中生, 大学生, 老人, 老年人, 萝莉, 正太"),
    *_terms("person", "age_gender", "成年女性, 成年男性, 年轻女性, 年轻男性, 中年女性, 中年男性, 老年女性, 老年男性"),
    *_terms("body_part", "face", "面部, 脸部, 面容, 五官, 眼睛, 鼻子, 嘴唇, 嘴巴, 牙齿, 舌头, 头部, 脖子"),
    *_terms("body_part", "hair", "头发, 发型, 刘海, 马尾, 长发, 短发, 卷发, 直发, 黑发, 金发, 白发"),
    *_terms("body_part", "chest", "胸部, 乳房, 乳头, 乳晕, 乳沟, 胸口, 大胸, 小胸, 平胸, 大乳晕, 小乳晕, 粉色乳头, 褐色乳头, 腰部, 腹部, 臀部, 大腿, 小腿, 双手, 手部, 手臂, 手指, 脚部, 膝盖, 背部, 头顶, 血管"),
    *_terms("adult_anatomy", "chest", "木瓜奶"),
    *_terms("adult_anatomy", "genital", "阴道, 小穴, 阴部, 私处, 外阴, 阴唇, 阴蒂, 阴茎, 大阴茎, 小阴茎, 粗大阴茎, 黑色阴茎, 红色阴茎, 鸡鸡, 弟弟, 肉棒, 龟头, 粉色龟头, 阴毛, 浓密阴毛, 稀疏阴毛, 无阴毛, 黑色阴毛"),
    *_terms("adult_anatomy", "anus", "肛门, 菊花, 后庭"),
    *_terms("adult_anatomy", "fluid", "精液, 精子, 白浊, 体液"),
    *_terms("adult_theme", "nudity_change", "脱衣, 去衣, 脱光"),
    *_terms("adult_theme", "adult_device", "飞机杯, 鸡巴套子, 假阳具, 情趣玩具, 肛塞, 跳蛋, 避孕套"),
    *_terms("adult_theme", "adult_topic", "内射, 颜射, 羞辱, ntr, bdsm, 捆绑, 肉便器, 怀孕, 色情, 母狗, 母猪"),
    *_terms("adult_theme", "role", "性奴, 性奴隶, 妓女"),
    *_terms("adult_theme", "humiliation", "荡妇, 贱货, 贱人, 骚逼, 骚货"),
    *_terms("adult_theme", "fetish", "精厕, 精厠, 精盆, 调教, 吞精喝尿, 吞精, 喝尿"),
    *_terms("adult_theme", "adult_behavior", "口交, 性交, 插入, 抽插, 自慰, 射精, 深喉, 后入, 骑乘"),
    *_terms("pose_action", "pose", "站立, 站姿, 坐姿, 躺姿, 躺在床上, 趴着, 趴姿, 跪姿, 跪在地上, 坐在地上, 深蹲, 蹲下, 弯腰, 弯曲, 抬腿, 张腿, 双腿分开, 双腿抬起, 双腿弯曲, 双腿并拢, m字开腿, 背对, 正面, 侧身, 直立, 倾斜, 狗式, 女上位"),
    *_terms("pose_action", "motion", "拥抱, 亲吻, 跳舞, 奔跑, 行走, 转身, 举手, 伸手, 扶着, 看向镜头, 手势"),
    *_terms("appearance", "hair", "无毛, 发色, 波波头"),
    *_terms("appearance", "skin", "光滑, 湿润, 皮肤, 肤色, 纹理"),
    *_terms("appearance", "body_shape", "丰满, 饱满, 苗条, 纤细, 细腰, 肌肉, 特征, 容貌, 年轻, 可爱, 无赘肉"),
    *_terms("appearance", "makeup", "妆容, 口红"),
    *_terms("clothing", "garment", "衣服, 上衣, 裙子, 短裙, 长裙, 内衣, 胸罩, 内裤, 丝袜, 袜子, 鞋子, 高跟鞋, 制服, 泳衣, 裸体, 半裸, 服饰, 布料, 材质, 透视"),
    *_terms("clothing", "clothing_change", "换装"),
    *_terms("clothing", "accessory", "眼镜, 项链, 耳环, 手套, 帽子, 头饰, 纹身, 颈圈, 蕾丝, calvin klein"),
    *_terms("expression", "independent", "表情, 神态, 微笑, 大笑, 哭泣, 害羞, 脸红, 惊讶, 闭眼, 睁眼, 凝视, 眼神, 翻白眼, 张着嘴, 阿嘿颜"),
    *_terms("scene", "place", "房子, 房间, 卧室, 客厅, 浴室, 厨房, 街道, 森林, 海边, 沙滩, 学校, 办公室, 酒店, ktv, 床, 地上"),
    *_terms("scene", "background", "背景, 环境, 室内, 室外, 夜晚, 白天, 阳光, 雨天, 灯光, 阴影, 手机, 屏幕, 桌子"),
    *_terms("camera", "camera_angle", "镜头, 鏡頭, 视角, 角度, pov, 俯视, 俯拍, 仰视, 侧面, 正面, 背面, 特写, 拍摄, 摄影, 相机"),
    *_terms("camera", "shot", "全身, 半身, 近景, 远景, 全景, 构图, 景深, 对焦, 焦点, 距离, 画面"),
    *_terms("camera", "frame_space", "空间, 向下"),
    *_terms("style_quality", "lighting", "光影, 光线, 光照, 柔光, 逆光, 自然光"),
    *_terms("style_quality", "quality", "写实, 真实, 高清, 高质量, 精细, 细节, 电影感, 胶片感, 画质, 色彩, 色调, 明亮, 清晰, 模糊, 流畅, 杰作, realistic, photorealistic, detailed"),
)


ALIAS_RULE_SEEDS: tuple[AliasRuleSeed, ...] = (
    AliasRuleSeed("面部", ("脸部", "面容", "face", "facial", "얼굴"), "body_part", "face"),
    AliasRuleSeed("眼睛", ("眼部", "eyes", "eye", "눈"), "body_part", "face"),
    AliasRuleSeed("嘴唇", ("唇部", "嘴巴", "lips", "mouth", "입술"), "body_part", "face"),
    AliasRuleSeed("头发", ("发丝", "hair", "헤어", "머리카락"), "body_part", "hair"),
    AliasRuleSeed("乳房", ("胸部", "breasts", "breast", "boobs", "boob", "tits", "가슴", "奶子"), "adult_anatomy", "chest"),
    AliasRuleSeed(
        "大胸",
        (
            "大奶",
            "大乳",
            "巨乳",
            "爆乳",
            "丰满胸部",
            "豐滿胸部",
            "胸很大",
            "胸围很大",
            "胸圍很大",
            "胸大",
            "full breasts",
            "full breast",
            "full bust",
            "large breasts",
            "big breasts",
            "big boobs",
        ),
        "adult_anatomy",
        "chest",
    ),
    AliasRuleSeed(
        "小胸",
        (
            "小奶",
            "小乳",
            "微乳",
            "胸小",
            "胸很小",
            "贫乳",
            "貧乳",
            "small breasts",
            "small breast",
            "small boobs",
            "small tits",
            "small chest",
        ),
        "adult_anatomy",
        "chest",
    ),
    AliasRuleSeed("平胸", ("无胸", "無胸", "flat chest", "flat breasts", "flatchested"), "adult_anatomy", "chest"),
    AliasRuleSeed("乳晕", ("乳暈", "areola", "areolas", "areolae"), "adult_anatomy", "chest"),
    AliasRuleSeed("大乳晕", ("大乳暈", "乳暈大", "大areola", "large areola", "large areolas"), "adult_anatomy", "chest"),
    AliasRuleSeed("小乳晕", ("小乳暈", "乳暈偏小", "small areola", "small areolas", "small areolae"), "adult_anatomy", "chest"),
    AliasRuleSeed("乳头", ("奶头", "nipples", "nipple", "유두"), "adult_anatomy", "chest"),
    AliasRuleSeed("粉色乳头", ("粉色奶頭", "粉紅色乳頭", "pink nipples", "pink nipple"), "adult_anatomy", "chest"),
    AliasRuleSeed("褐色乳头", ("褐色奶頭", "咖啡色奶頭", "棕色乳头", "棕色奶頭", "brown nipples", "brown nipple"), "adult_anatomy", "chest"),
    AliasRuleSeed("乳沟", ("cleavage",), "adult_anatomy", "chest"),
    AliasRuleSeed("脸颊", ("cheek", "cheeks"), "body_part", "face"),
    AliasRuleSeed("臀部", ("hip", "hips", "ass", "butt", "buttocks"), "body_part", ""),
    AliasRuleSeed("手臂", ("arm", "arms"), "body_part", "limb"),
    AliasRuleSeed("手指", ("finger", "fingers"), "body_part", "limb"),
    AliasRuleSeed("脚部", ("foot", "feet"), "body_part", "limb"),
    AliasRuleSeed("膝盖", ("knee", "knees"), "body_part", "limb"),
    AliasRuleSeed("阴道", ("小穴", "阴部", "私处", "外阴", "陰道", "陰部", "vagina", "pussy", "cunt", "보지", "질"), "adult_anatomy", "genital"),
    AliasRuleSeed("阴唇", ("labia",), "adult_anatomy", "genital"),
    AliasRuleSeed("阴茎", ("鸡鸡", "弟弟", "肉棒", "陰茎", "陰莖", "penis", "cock", "dick", "자지", "음경"), "adult_anatomy", "genital"),
    AliasRuleSeed("大阴茎", ("大陰莖", "大鸡巴", "大雞巴", "big penis", "large penis", "big cock", "large cock"), "adult_anatomy", "genital"),
    AliasRuleSeed("小阴茎", ("小陰莖", "小鸡巴", "小雞巴", "small penis", "small cock", "small dick"), "adult_anatomy", "genital"),
    AliasRuleSeed("粗大阴茎", ("粗大雞巴", "粗大鸡巴", "粗壮鸡巴", "粗壯雞巴", "thick penis", "thick cock"), "adult_anatomy", "genital"),
    AliasRuleSeed("黑色阴茎", ("黑色陰莖", "黑色鸡巴", "黑色雞巴", "black penis", "black cock"), "adult_anatomy", "genital"),
    AliasRuleSeed("红色阴茎", ("紅色陰莖", "红色鸡巴", "紅色雞巴", "red penis", "red cock"), "adult_anatomy", "genital"),
    AliasRuleSeed("肛门", ("菊花", "后庭", "anus", "asshole", "항문"), "adult_anatomy", "anus"),
    AliasRuleSeed("阴毛", ("陰毛", "耻毛", "恥毛", "pubic hair", "bush"), "adult_anatomy", "genital"),
    AliasRuleSeed("浓密阴毛", ("濃密陰毛", "阴毛浓密", "陰毛濃密", "阴毛茂盛", "陰毛茂盛", "多阴毛", "多陰毛", "下体多阴毛", "下體多陰毛"), "adult_anatomy", "genital"),
    AliasRuleSeed("稀疏阴毛", ("稀疏陰毛", "少量阴毛", "少量陰毛", "少许阴毛", "少許陰毛", "少阴毛", "少陰毛", "阴毛量偏少", "陰毛量偏少"), "adult_anatomy", "genital"),
    AliasRuleSeed("无阴毛", ("無陰毛", "没有阴毛", "沒有陰毛", "无毛阴部", "無毛陰部", "下体无毛", "下體無毛", "hairless pussy"), "adult_anatomy", "genital"),
    AliasRuleSeed("黑色阴毛", ("黑色陰毛", "black pubic hair"), "adult_anatomy", "genital"),
    AliasRuleSeed("精液", ("精子", "白浊", "semen", "cum", "정액"), "adult_anatomy", "fluid"),
    AliasRuleSeed("单人", ("一人", "一位", "solo", "one person"), "person", "people_count"),
    AliasRuleSeed("单男", ("1boy",), "person", "people_count"),
    AliasRuleSeed("单女", ("1girl", "1female"), "person", "people_count"),
    AliasRuleSeed("双人", ("两人", "俩人", "二人", "2people", "two people"), "person", "people_count"),
    AliasRuleSeed("三人", ("3people", "three people"), "person", "people_count"),
    AliasRuleSeed("多人", ("many people", "multiple people"), "person", "people_count"),
    AliasRuleSeed("性交", ("sex", "intercourse", "fuck", "fucking", "fucked", "交合", "正在进行性交", "操死我"), "adult_theme", "adult_behavior"),
    AliasRuleSeed("口交", ("blowjob", "oral", "fellatio", "深喉", "吹箫"), "adult_theme", "adult_behavior"),
    AliasRuleSeed("自慰", ("masturbation", "手淫", "自摸"), "adult_theme", "adult_behavior"),
    AliasRuleSeed("射精", ("ejaculation", "射出", "ejaculate", "cumming"), "adult_theme", "adult_behavior"),
    AliasRuleSeed("插入", ("penetration", "insertion", "inserts", "penetrating", "penetrated", "inserted"), "adult_theme", "adult_behavior"),
    AliasRuleSeed("抽插", ("活塞运动", "抽送", "pounding", "thrusting", "pump"), "adult_theme", "adult_behavior"),
    AliasRuleSeed("狗式", ("doggy", "doggy style"), "pose_action", "pose"),
    AliasRuleSeed(
        "双腿分开",
        ("双腿张开", "双腿打开", "双腿叉开", "雙腿張開", "雙腿打開", "雙腿叉開", "雙腿大幅打開", "雙腿被大大分開"),
        "pose_action",
        "pose",
    ),
    AliasRuleSeed("双腿抬起", ("雙腿抬起",), "pose_action", "pose"),
    AliasRuleSeed("双腿弯曲", ("雙腿彎曲",), "pose_action", "pose"),
    AliasRuleSeed("弯腰", ("彎腰", "度弯腰", "度彎腰", "高度彎腰", "高度弯腰"), "pose_action", "pose"),
    AliasRuleSeed(
        "m字开腿",
        (
            "m字腿",
            "m 字腿",
            "m字開腿",
            "m字開腳",
            "m字型",
            "m字形",
            "m字形状",
            "m字形狀",
            "m型腿",
            "m形腿",
            "m型开腿",
            "m形开腿",
            "m型姿势",
            "m型姿勢",
            "m字姿势",
            "m字姿勢",
            "腿成m形",
            "腿成m型",
            "腿呈m形",
            "腿呈m型",
            "双腿呈m字型",
            "雙腿呈m字型",
            "双腿呈m型",
            "雙腿呈m型",
        ),
        "pose_action",
        "pose",
    ),
    AliasRuleSeed("女上位", ("cowgirl",), "pose_action", "pose"),
    AliasRuleSeed("跪姿", ("kneeling",), "pose_action", "pose"),
    AliasRuleSeed("躺姿", ("lying",), "pose_action", "pose"),
    AliasRuleSeed("站姿", ("standing",), "pose_action", "pose"),
    AliasRuleSeed("无毛", ("hairless", "shaved", "光滑无毛"), "appearance", "hair"),
    AliasRuleSeed(
        "木瓜奶",
        ("木瓜形", "木瓜狀", "木瓜胸", "木瓜式奶", "papaya breasts", "papaya breast"),
        "adult_anatomy",
        "chest",
    ),
    AliasRuleSeed("脱衣", ("去衣", "脱光", "undress", "undressing", "strip", "stripped", "stripping", "undressed"), "adult_theme", "nudity_change"),
    AliasRuleSeed("换装", ("换衣", "換衣"), "clothing", "clothing_change"),
    AliasRuleSeed("袜子", ("襪子", "袜", "襪", "sock", "socks", "socked", "保留襪子", "袜子保留", "襪子保留", "同樣的襪子", "襪子等"), "clothing", "garment"),
    AliasRuleSeed("丝袜", ("絲襪", "絲袜", "丝襪", "stocking", "stockings", "stockinged", "silk stockings", "nylon stockings"), "clothing", "garment"),
    AliasRuleSeed("黑色丝袜", ("黑丝", "黑丝袜", "黑絲襪", "黑色絲襪", "black stockings", "black stocking", "black silk stockings", "black nylon stockings", "腿上穿著黑色絲襪", "只有穿黑色絲襪"), "clothing", "color_garment"),
    AliasRuleSeed("白色丝袜", ("白丝", "白丝袜", "白絲襪", "白色絲襪", "穿上白絲襪", "white stockings", "white stocking", "white silk stockings"), "clothing", "color_garment"),
    AliasRuleSeed("透明丝袜", ("透明絲襪", "透肤丝袜", "透膚絲襪", "transparent stockings", "sheer stockings"), "clothing", "color_garment"),
    AliasRuleSeed("半透明丝袜", ("半透明絲襪", "半透絲襪", "semi transparent stockings", "semi-transparent stockings", "腳穿半透明黑絲襪"), "clothing", "color_garment"),
    AliasRuleSeed("肉色丝袜", ("肉色絲襪", "nude stockings", "skin tone stockings", "skin-tone stockings", "skin colored stockings", "skin-colored stockings"), "clothing", "color_garment"),
    AliasRuleSeed("粉色丝袜", ("粉色絲襪", "pink stockings"), "clothing", "color_garment"),
    AliasRuleSeed("紫色丝袜", ("紫色絲襪", "穿紫色絲襪", "purple stockings"), "clothing", "color_garment"),
    AliasRuleSeed("红色丝袜", ("紅色絲襪", "红丝长袜", "red stockings"), "clothing", "color_garment"),
    AliasRuleSeed("绿色丝袜", ("綠色絲襪", "green stockings"), "clothing", "color_garment"),
    AliasRuleSeed("蓝色丝袜", ("藍色絲襪", "blue stockings"), "clothing", "color_garment"),
    AliasRuleSeed("灰色丝袜", ("灰色絲襪", "gray stockings", "grey stockings"), "clothing", "color_garment"),
    AliasRuleSeed("蕾丝袜", ("蕾絲絲襪", "蕾丝丝袜", "lace stockings"), "clothing", "garment_material"),
    AliasRuleSeed("黑色蕾丝袜", ("黑色蕾絲絲襪", "黑色吊帶蕾絲絲襪", "高筒蕾絲黑絲襪", "black lace stockings"), "clothing", "color_garment"),
    AliasRuleSeed("渔网袜", ("鱼网袜", "魚網襪", "网袜", "網襪", "fishnet", "fishnets", "fishnet stockings", "mesh stockings"), "clothing", "garment"),
    AliasRuleSeed("破洞渔网袜", ("破洞鱼网袜", "破洞魚網襪", "破洞网袜", "破洞網襪", "torn fishnet stockings", "ripped fishnet stockings"), "clothing", "garment_state"),
    AliasRuleSeed("黑色渔网袜", ("黑色网袜", "黑色網襪", "黑色鱼网袜", "黑色魚網襪", "black fishnet", "black fishnets", "black fishnet stockings"), "clothing", "color_garment"),
    AliasRuleSeed("白色网袜", ("白色網襪", "白色鱼网袜", "white fishnet", "white fishnets", "white fishnet stockings"), "clothing", "color_garment"),
    AliasRuleSeed("连裤网袜", ("連褲網襪", "穿著黑色連褲網襪", "fishnet pantyhose", "fishnet tights"), "clothing", "garment"),
    AliasRuleSeed("吊带网袜", ("吊帶網襪", "穿著網格吊帶襪", "garter fishnet stockings"), "clothing", "garment"),
    AliasRuleSeed("黑色吊带网袜", ("黑色吊帶網襪", "穿著黑色吊帶網襪", "black garter fishnet stockings"), "clothing", "color_garment"),
    AliasRuleSeed("连裤袜", ("連褲襪", "裤袜", "褲襪", "pantyhose", "tights"), "clothing", "garment"),
    AliasRuleSeed("黑色连裤袜", ("黑色裤袜", "黑色褲襪", "黑丝裤袜", "連褲黑絲襪", "只保留黑丝裤袜", "black pantyhose", "black tights"), "clothing", "color_garment"),
    AliasRuleSeed("白色连裤袜", ("白色裤袜", "白色褲襪", "白丝裤袜", "white pantyhose", "white tights"), "clothing", "color_garment"),
    AliasRuleSeed("肉色连裤袜", ("肉丝裤袜", "肉色裤袜", "nude pantyhose", "skin tone pantyhose"), "clothing", "color_garment"),
    AliasRuleSeed("连体袜", ("連體襪", "连体丝袜", "連體絲襪", "bodystocking", "body stocking", "body stockings", "黑色透肤连体袜", "白色连体袜"), "clothing", "garment"),
    AliasRuleSeed("长筒袜", ("長筒襪", "长袜", "長襪", "高筒袜", "高筒襪", "高統襪", "thighhigh", "thighhighs", "thigh high stockings", "thigh-high stockings"), "clothing", "garment"),
    AliasRuleSeed("过膝袜", ("過膝襪", "over knee socks", "over-knee socks", "knee high socks", "knee-high socks", "knee socks"), "clothing", "garment"),
    AliasRuleSeed("白色过膝袜", ("白色過膝襪", "她穿白色过膝襪", "加長白色過膝襪", "白色過膝羊毛襪", "穿著白色過膝長襪", "white over-knee socks", "white knee-high socks"), "clothing", "color_garment"),
    AliasRuleSeed("黑色过膝袜", ("黑色過膝襪", "她穿的黑色過膝襪", "黑色长袜", "黑色長襪", "黑色高筒袜", "黑色高統襪", "black over-knee socks", "black knee-high socks"), "clothing", "color_garment"),
    AliasRuleSeed("白色过膝丝袜", ("白色過膝絲襪", "過膝白絲襪", "白色絲綢過膝絲襪", "白色透明過膝絲襪", "穿白色过膝袜", "white thigh-high stockings"), "clothing", "color_garment"),
    AliasRuleSeed("黑色过膝丝袜", ("黑色過膝絲襪", "穿黑色过膝絲袜", "穿黑色过膝絲襪", "穿黑色过膝網袜", "black thigh-high stockings"), "clothing", "color_garment"),
    AliasRuleSeed("黑色透明过膝丝袜", ("黑色透明過膝絲襪", "black sheer thigh-high stockings"), "clothing", "color_garment"),
    AliasRuleSeed("浅蓝色过膝袜", ("淺藍色過膝長筒襪", "light blue thigh-high socks"), "clothing", "color_garment"),
    AliasRuleSeed("短袜", ("短襪", "short socks", "ankle socks", "穿小短白袜"), "clothing", "garment"),
    AliasRuleSeed("白色袜子", ("白袜", "白襪", "穿白袜", "穿白襪", "著白襪", "腳穿白襪", "小白袜", "white socks"), "clothing", "color_garment"),
    AliasRuleSeed("黑色袜子", ("黑袜", "黑襪", "black socks"), "clothing", "color_garment"),
    AliasRuleSeed("白色棉袜", ("白色棉襪", "白色女棉袜", "脚穿白色棉袜", "脚上穿白色的棉袜", "女子穿著白色棉襪", "左邊穿純白棉襪", "只穿了双白色棉袜", "white cotton socks"), "clothing", "color_garment"),
    AliasRuleSeed("白色短袜", ("白色短襪", "穿白色短棉袜", "脚上穿白色短棉袜", "white ankle socks", "white short socks"), "clothing", "color_garment"),
    AliasRuleSeed("白色中筒袜", ("白色中筒襪", "搭配白色中筒袜", "white crew socks"), "clothing", "color_garment"),
    AliasRuleSeed("蓝色短袜", ("藍色短襪", "blue short socks"), "clothing", "color_garment"),
    AliasRuleSeed("吊带袜", ("吊帶襪", "garter stockings"), "clothing", "garment"),
    AliasRuleSeed("吊带丝袜", ("吊帶絲襪", "garter stockings with silk"), "clothing", "garment"),
    AliasRuleSeed("黑色吊带丝袜", ("黑色吊帶絲襪", "黑色吊帶襪", "black garter stockings"), "clothing", "color_garment"),
    AliasRuleSeed("白色吊带丝袜", ("白色吊帶絲襪", "white garter stockings"), "clothing", "color_garment"),
    AliasRuleSeed("蕾丝吊带袜", ("蕾絲吊帶襪", "蕾絲吊帶過膝襪", "穿著蕾絲吊帶襪", "穿著蕾絲吊帶絲襪", "精緻的吊帶襪黑絲", "lace garter stockings"), "clothing", "garment_material"),
    AliasRuleSeed("吊袜带", ("吊襪帶", "garter", "garters", "garter belt"), "clothing", "accessory"),
    AliasRuleSeed("开档丝袜", ("开档袜", "開檔襪", "半透纱织开档袜", "crotchless stockings", "crotchless pantyhose"), "clothing", "garment_state"),
    AliasRuleSeed("乳胶过膝袜", ("透明乳膠過膝襪", "白色矽膠過膝襪", "latex thigh-high stockings"), "clothing", "garment_material"),
    AliasRuleSeed("堆堆袜", ("脚上白色堆堆袜", "搭配白色堆堆袜", "loose socks"), "clothing", "garment"),
    AliasRuleSeed("破洞过膝袜", ("破烂白色高筒襪", "torn thigh-high socks", "ripped thigh-high socks"), "clothing", "garment_state"),
    AliasRuleSeed("无袜子", ("没穿袜子", "沒穿襪子", "不穿袜子", "不穿襪子", "no socks", "without socks"), "clothing", "clothing_change"),
    AliasRuleSeed("无丝袜", ("移除丝袜", "移除絲襪", "remove stockings", "without stockings"), "clothing", "clothing_change"),
    AliasRuleSeed("机器", ("machine",), "adult_theme", "adult_device"),
    AliasRuleSeed("胸罩", ("bra",), "clothing", "garment"),
    AliasRuleSeed("蕾丝", ("lace",), "clothing", "accessory"),
    AliasRuleSeed("颈圈", ("collar",), "clothing", "accessory"),
    AliasRuleSeed("Calvin Klein", ("calvin", "klein"), "clothing", "accessory"),
    AliasRuleSeed("背景保持", ("原图背景", "背景不变", "保持背景"), "preservation", "background_preserve"),
    AliasRuleSeed("皮肤", ("skin",), "appearance", "skin"),
    AliasRuleSeed("衣服", ("clothes", "clothing", "cloth"), "clothing", "garment"),
    AliasRuleSeed("口红", ("lipstick",), "appearance", "makeup"),
    AliasRuleSeed("妆容", ("makeup",), "appearance", "makeup"),
    AliasRuleSeed("刘海", ("bangs",), "appearance", "hair"),
    AliasRuleSeed("波波头", ("bob",), "appearance", "hair"),
    AliasRuleSeed("无赘肉", ("没有一丝赘肉", "沒有一絲贅肉"), "appearance", "body_shape"),
    AliasRuleSeed("怀孕", ("懷孕", "懷著"), "adult_theme", "adult_topic"),
    AliasRuleSeed("裸体", ("全裸", "赤裸", "nude", "naked", "裸体的", "赤裸的", "一丝不挂", "一絲不掛"), "adult_theme", "nudity"),
    AliasRuleSeed("上身裸露", ("上半身裸", "上身赤裸", "上半身赤裸", "topless", "nude upper body"), "adult_theme", "nudity"),
    AliasRuleSeed("下身赤裸", ("下半身裸", "下身裸露", "下半身赤裸", "bottomless", "nude lower body"), "adult_theme", "nudity"),
    AliasRuleSeed("性奴", ("肉奴", "性奴隶", "性奴隸", "sex slave", "slave", "专用性奴", "專用性奴", "黑人性奴", "黑爹性奴", "母狗性奴", "性奴便器", "性奴秘书", "奴隶编号"), "adult_theme", "role"),
    AliasRuleSeed("妓女", ("娼妓", "妓女证", "妓女證", "妓女专用", "妓女專用", "prostitute"), "adult_theme", "role"),
    AliasRuleSeed("荡妇", ("蕩婦", "淫妇", "淫婦", "slut", "贱货", "賤貨", "贱人", "賤人", "贱婊子", "贱逼", "贱狗", "贱畜", "贱奴", "贱妇", "淫贱", "骚逼", "骚货", "骚浪贱", "臭骚逼", "贱骚货", "bitch", "whore"), "adult_theme", "humiliation"),
    AliasRuleSeed("母狗", ("母犬",), "adult_theme", "humiliation"),
    AliasRuleSeed("母猪", ("母豬",), "adult_theme", "humiliation"),
    AliasRuleSeed("飞机杯", ("飛機杯", "人肉飞机杯", "人形飞机杯", "黑爹的飞机杯", "爸爸的飞机杯", "专属飞机杯", "專屬飞机杯", "fleshlight", "onahole"), "adult_theme", "adult_device"),
    AliasRuleSeed("鸡巴套子", ("雞巴套子", "黑爹专属鸡巴套子", "主人鸡巴套子", "大众鸡巴套子"), "adult_theme", "adult_device"),
    AliasRuleSeed("假阳具", ("假陽具", "假阳具等等", "dildo"), "adult_theme", "adult_device"),
    AliasRuleSeed("精厕", ("精厠", "特级精厕", "公共精厕", "免费精厕", "廉价精厕", "黑人精厕", "专属精厕", "黑爹专属精厕", "主人的精厕", "精液厕所"), "adult_theme", "fetish"),
    AliasRuleSeed("精盆", ("精液盆子", "精液盆", "公共精盆"), "adult_theme", "fetish"),
    AliasRuleSeed("调教", ("調教", "调教成功", "调教完成", "欢淫调教", "药物调教"), "adult_theme", "fetish"),
    AliasRuleSeed("吞精喝尿", ("吞精", "喝尿", "吞精喝尿水"), "adult_theme", "fetish"),
    AliasRuleSeed("肉便器", ("母狗便器", "母猪便器", "母狗肉便器", "母猪肉便器", "免费肉便器", "公共肉便器", "公用肉便器", "rbq"), "adult_theme", "adult_topic"),
    AliasRuleSeed("色情", ("淫乱", "淫蕩", "淫荡", "淫欲", "淫靡", "porn", "porno", "pornographic"), "adult_theme", "adult_topic"),
    AliasRuleSeed(
        "翻白眼",
        (
            "阿颜黑",
            "阿顏黑",
            "阿黑颜",
            "阿黑顏",
            "阿嘿颜",
            "阿嘿顏",
            "反白眼",
            "翻着白眼",
            "翻著白眼",
            "翻起白眼",
            "翻出白眼",
            "双眼翻白",
            "双眼翻着白眼",
            "双眼向上翻",
            "ahegao",
            "ahego",
            "ahegeo",
            "aheagao",
            "aheago",
            "ahegoface",
        ),
        "expression",
        "expression",
    ),
    AliasRuleSeed("双手", ("hand", "hands"), "body_part", "limb"),
    AliasRuleSeed("头部", ("head",), "body_part", "face"),
    AliasRuleSeed("深蹲", ("蹲姿", "蹲下", "squat", "squatting"), "pose_action", "pose"),
    AliasRuleSeed("背对", ("背面", "from behind", "rear view"), "pose_action", "pose"),
    AliasRuleSeed("正面", ("正视", "front view"), "camera", "camera_angle"),
    AliasRuleSeed("特写", ("closeup", "close-up", "近景"), "camera", "shot"),
    AliasRuleSeed("镜头", ("鏡頭", "camera", "shot"), "camera", "camera_angle"),
    AliasRuleSeed("视角", ("視角", "viewpoint", "perspective"), "camera", "camera_angle"),
    AliasRuleSeed("角度", ("angle", "angles"), "camera", "camera_angle"),
    AliasRuleSeed("焦点", ("focus",), "camera", "shot"),
    AliasRuleSeed("卧室", ("bedroom",), "scene", "place"),
    AliasRuleSeed("床", ("bed",), "scene", "place"),
    AliasRuleSeed("地面", ("floor", "ground"), "scene", "place"),
    AliasRuleSeed("ktv", (), "scene", "place"),
    AliasRuleSeed("写实", ("realistic", "photorealistic", "真实感"), "style_quality", "quality"),
    AliasRuleSeed("高清", ("highres", "high resolution", "高分辨率"), "style_quality", "quality"),
    AliasRuleSeed("画质", ("畫質", "品质", "品質", "quality", "最优质量", "最優質量"), "style_quality", "quality"),
    AliasRuleSeed("光影", ("光线", "光照", "lighting"), "style_quality", "lighting"),
    AliasRuleSeed("清晰", ("clear", "clearly"), "style_quality", "quality"),
    AliasRuleSeed("细节", ("detail", "details"), "style_quality", "quality"),
    AliasRuleSeed("光泽", ("glossy",), "style_quality", "quality"),
    AliasRuleSeed("电影感", ("film", "grain"), "style_quality", "quality"),
    AliasRuleSeed("女性", ("female",), "person", "gender"),
    AliasRuleSeed("男性", ("male",), "person", "gender"),
    AliasRuleSeed("男人", ("man",), "person", "gender"),
    AliasRuleSeed("亚洲人", ("亚洲", "亞洲", "亚裔", "亞裔", "asian"), "person", "ethnicity_country"),
    AliasRuleSeed("东亚人", ("东亚", "東亞"), "person", "ethnicity_country"),
    AliasRuleSeed("中国人", ("中国", "中國", "中國人", "chinese"), "person", "ethnicity_country"),
    AliasRuleSeed("日本人", ("日本", "japanese"), "person", "ethnicity_country"),
    AliasRuleSeed("韩国人", ("韩国", "韓國", "韓國人", "korean"), "person", "ethnicity_country"),
    AliasRuleSeed("台湾", ("台灣", "臺灣"), "person", "ethnicity_country"),
    AliasRuleSeed("台湾人", ("台灣人", "臺灣人", "taiwanese"), "person", "ethnicity_country"),
    AliasRuleSeed("欧美人", ("欧美", "歐美"), "person", "ethnicity_country"),
    AliasRuleSeed("东亚女性", ("东亚女人", "东亚女生", "東亞女性", "東亞女人", "東亞女生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("东亚男性", ("东亚男人", "东亚男生", "東亞男性", "東亞男人", "東亞男生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed(
        "亚洲女性",
        ("亚洲女人", "亚洲女生", "亞洲女性", "亞洲女人", "亞洲女生", "亚裔女性", "亞裔女性", "亚裔女人", "亞裔女人", "亚裔女生", "亞裔女生"),
        "person",
        "ethnicity_age_gender",
    ),
    AliasRuleSeed(
        "亚洲男性",
        ("亚洲男人", "亚洲男生", "亞洲男性", "亞洲男人", "亞洲男生", "亚裔男性", "亞裔男性", "亚裔男人", "亞裔男人", "亚裔男生", "亞裔男生"),
        "person",
        "ethnicity_age_gender",
    ),
    AliasRuleSeed("中国女性", ("中国女人", "中国女生", "中國女性", "中國女人", "中國女生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("中国男性", ("中国男人", "中国男生", "中國男性", "中國男人", "中國男生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("日本女性", ("日本女人", "日本女生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("日本男性", ("日本男人", "日本男生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("韩国女性", ("韩国女人", "韩国女生", "韓國女性", "韓國女人", "韓國女生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("韩国男性", ("韩国男人", "韩国男生", "韓國男性", "韓國男人", "韓國男生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("台湾女性", ("台湾女人", "台湾女生", "台灣女性", "台灣女人", "台灣女生", "臺灣女性", "臺灣女人", "臺灣女生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("台湾男性", ("台湾男人", "台湾男生", "台灣男性", "台灣男人", "台灣男生", "臺灣男性", "臺灣男人", "臺灣男生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("欧美女性", ("欧美女人", "欧美女生", "歐美女性", "歐美女人", "歐美女生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("欧美男性", ("欧美男人", "欧美男生", "歐美男性", "歐美男人", "歐美男生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("黑人女性", ("黑人女人", "黑人女生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("黑人男性", ("黑人男人", "黑人男生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("白人女性", ("白人女人", "白人女生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("白人男性", ("白人男人", "白人男生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("非洲女性", ("非洲女人", "非洲女生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("非洲男性", ("非洲男人", "非洲男生"), "person", "ethnicity_age_gender"),
    AliasRuleSeed("老年男性", ("老年男人", "老年男生"), "person", "age_gender"),
    AliasRuleSeed("老年女性", ("老年女人", "老年女生"), "person", "age_gender"),
    AliasRuleSeed("老年人", ("老人",), "person", "age"),
    AliasRuleSeed("年轻女性", ("年輕女性", "年轻女人", "年輕女人", "年轻女生", "年輕女生"), "person", "age_gender"),
    AliasRuleSeed("年轻男性", ("年輕男性", "年轻男人", "年輕男人", "年轻男生", "年輕男生"), "person", "age_gender"),
    AliasRuleSeed("成年女性", ("成年女人", "成熟女性", "成熟女人"), "person", "age_gender"),
    AliasRuleSeed("成年男性", ("成年男人",), "person", "age_gender"),
    AliasRuleSeed("中年女性", ("中年女人",), "person", "age_gender"),
    AliasRuleSeed("中年男性", ("中年男人", "中年男生"), "person", "age_gender"),
    AliasRuleSeed("萝莉", ("蘿莉",), "person", "age"),
)


DEMOGRAPHIC_ALLOWED_TERMS = {
    "男孩",
    "女孩",
    "小男孩",
    "小女孩",
    "少年",
    "少女",
    "儿童",
    "孩子",
    "未成年",
    "小学生",
    "初中生",
    "中学生",
    "高中生",
    "大学生",
    "老人",
    "老年人",
    "萝莉",
    "蘿莉",
    "正太",
}

AGE_BASE_TERMS = DEMOGRAPHIC_ALLOWED_TERMS | {
    "男高中生",
    "女高中生",
    "初高中生",
    "幼童",
    "幼女",
}

AGE_GENDER_RE = re.compile(
    r"^(年轻|年輕|青年|中年|老年|成年|成熟|年长|年長|幼小|年幼)"
    r"(男性|男人|男生|女人|女性|女生|女孩|男孩|少年|少女|老人)$"
)
ETHNICITY_AGE_GENDER_RE = re.compile(
    r"^(亚洲|亞洲|亚裔|亞裔|东亚|東亞|黑人|非洲|白人|欧美|歐美|台湾|台灣|臺灣|日本|韩国|韓國|中国|中國)"
    r"(小男孩|男孩|小女孩|女孩|少年|少女|男性|男人|男生|女性|女人|女生|老人|老年男人|老年男性)$"
)
NUMERIC_AGE_PERSON_RE = re.compile(
    r"^[0-9一二三四五六七八九十兩两]+[岁歲][\u3400-\u9fff]{0,8}"
    r"(男孩|女孩|男性|女性|男人|女人|男生|女生|少年|少女|儿童|小男孩|小女孩)$"
)


NOISE_LATIN_WORDS = {
    "all",
    "back",
    "exact",
    "full",
    "raw",
    "same",
    "small",
    "light",
    "dry",
    "mostly",
    "from",
    "with",
    "into",
    "onto",
    "this",
    "that",
    "than",
    "very",
    "lora",
    "video",
    "movie",
    "photo",
    "image",
    "picture",
    "pictures",
    "are",
    "is",
    "was",
    "were",
    "has",
    "have",
    "had",
    "she",
    "her",
    "his",
    "him",
    "they",
    "them",
    "also",
    "each",
    "every",
    "both",
    "but",
    "being",
    "make",
    "change",
    "adjust",
    "amount",
    "area",
    "around",
    "between",
    "below",
    "above",
    "against",
    "inside",
    "outside",
    "bottom",
    "front",
    "left",
    "right",
    "down",
    "out",
    "open",
    "close",
    "closed",
    "low",
    "deep",
    "long",
    "large",
    "big",
    "huge",
    "heavy",
    "highly",
    "fully",
    "clearly",
    "directly",
    "angle",
    "angles",
    "background",
    "body",
    "bodies",
    "character",
    "cloth",
    "clothes",
    "clothing",
    "composition",
    "environment",
    "expression",
    "expressions",
    "face",
    "faces",
    "facial",
    "female",
    "focus",
    "garment",
    "garments",
    "girl",
    "girls",
    "guy",
    "hair",
    "lady",
    "male",
    "man",
    "men",
    "iphone",
    "person",
    "people",
    "scene",
    "shot",
    "skin",
    "subject",
    "eos",
    "a7r",
}

NOISE_TERMS = {
    "动作迁移",
    "图生视频",
    "换脸",
    "视频",
    "图片",
    "图像",
    "照片",
    "帧率",
    "帧每秒",
    "采样器",
    "采样器使用",
    "步数",
    "提示词强度",
    "强度为",
    "技术参数",
    "参数",
    "木瓜",
    "直到视频结束",
    "秒视频",
    "视频开始",
    "帮我生成视频",
    "视频开始时",
    "视频用",
    "视频要求",
    "生成视频",
    "高帧率",
    "视频帧率设置为",
    "帧率高",
    "高帧率模拟",
    "低帧率",
    "慢速高帧率",
    "极高帧率",
    "附近",
    "变装",
    "小",
    "门",
    "双腿",
    "雙腿",
    "便器",
    "字腿",
    "型腿",
    "形腿",
    "字开腿",
    "字開腿",
    "字開腳",
    "腿成",
    "腿呈",
    "腿呈现",
    "腿呈現",
    "双腿呈",
    "雙腿呈",
    "两腿呈",
    "兩腿呈",
    "两条腿呈",
    "兩條腿呈",
    "张开双腿成",
    "張開雙腿成",
    "分开双腿成",
    "抬高双腿成",
    "字型腿",
    "字形腿",
    "度弯腰",
    "度彎腰",
    "度躬着",
    "度弓着",
    "型下蹲",
    "型蹲在椅子上",
    "字蹲",
    "字蹲着",
    "字宽开",
    "字寬開",
    "完全",
    "完整",
    "整体",
    "大小",
    "左右",
    "正常",
    "效果",
    "多余",
    "一個",
    "厘米",
    "首先",
    "突然",
    "设计",
    "分辨率",
    "解析度",
    "512p",
    "24fps",
    "35mm",
    "50mm",
    "85mm",
    "36d",
    "提示词",
    "写着",
    "字样",
    "红字",
    "文字",
    "水印",
    "下方写着",
    "去掉水印",
    "去水印",
    "去除右下角水印",
    "去除水印",
    "字体紧贴皮肤",
    "文字有大有小",
    "无水印",
    "横着写着",
    "照片下面写着",
    "生成的图像",
    "等字眼",
    "胸口写有",
    "渲染",
    "分镜",
    "无缝循环",
    "重绘幅度",
    "转场",
    "转换",
    "动图",
    "音频",
    "负提示",
    "权重",
    "重新生成",
    "封面",
    "分离",
    "变体",
    "变换",
    "合成",
    # Low-value tag terms: broad labels, process words, camera/technical words,
    # and long instruction fragments should not become automatic classification tags.
    "以图",
    "状态",
    "裁剪",
    "放大",
    "去除",
    "不要拉伸",
    "融合",
    "不改变光比",
    "表现力",
    "中性",
    "支配",
    "说话",
    "一直流到地面",
    "背景",
    "环境",
    "場景",
    "场景",
    "周围",
    "阴影",
    "设备",
    "旁边",
    "拥挤",
    "风景",
    "同样的場地",
    "私密",
    "机器",
    "拟声词",
    "展示",
    "反复",
    "晃动",
    "卷起",
    "摆姿势",
    "强烈",
    "速度",
    "倾斜",
    "呼吸",
    "强力",
    "修改",
    "更快",
    "等待",
    "头部稍微右傾",
    "角度",
    "构图",
    "镜头",
    "鏡頭",
    "焦点",
    "视角",
    "視角",
    "画面",
    "相机",
    "摄影",
    "拍摄",
    "人物",
    "角色",
    "主体",
    "一起",
    "女性",
    "女人",
    "女孩",
    "女生",
    "女士",
    "女子",
    "美女",
    "男性",
    "男人",
    "男生",
    "男子",
    "面部",
    "脸部",
    "臉部",
    "面容",
    "五官",
    "表情",
    "神态",
    "神情",
    "眼神",
    "身体",
    "身體",
    "头发",
    "发型",
    "发色",
    "肩宽",
    "身体结构",
    "解剖结构",
    "身体比例",
    "溢出",
    "露脸",
    "尖端",
    "闪光灯",
    "索尼a7r5",
    "单反",
    "單反",
    "焦距",
    "屁股离地较近",
    "少指",
    "多指",
    "头身",
    "手機",
    "手机",
    "多余肢体",
    "坏手",
    "兩隻腿抬高狀態",
    "型腿",
    "同一张脸",
    "她两条腿叉开来",
    "无套灌精",
    "左手比",
    "屁股朝着画面右边",
    "米色罗纹针织腿套",
    "左手叉腰",
    "脸部特征精准鎖定",
    "比例",
    "皮肤",
    "特征",
    "妝容",
    "身高",
    "狭窄",
    "封闭",
    "衣服",
    "服饰",
    "高清",
    "画质",
    "畫質",
    "清晰",
    "细节",
    "細節",
    "自然",
    "颜色",
    "色彩",
    "光影",
    "光线",
    "光線",
    "光照",
}

PROPER_NAME_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}的")
HASHLIKE_RE = re.compile(r"^[a-f0-9]{10,}$")
COMPACT_CJK_OR_HANGUL_KANA_RE = re.compile(r"^[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]+$")


def category_label(category_key: str) -> str:
    return TOKEN_CATEGORY_LABELS.get(category_key, category_key or "")


def subcategory_label(subcategory_key: str) -> str:
    return TOKEN_SUBCATEGORY_LABELS.get(subcategory_key, subcategory_key or "")


def _metadata(
    *,
    category_key: str,
    subcategory_key: str = "",
    source: str,
    seed_batch: str,
    notes: str = "",
) -> dict[str, str]:
    return {
        "category_key": category_key,
        "category_label": category_label(category_key),
        "subcategory_key": subcategory_key,
        "subcategory_label": subcategory_label(subcategory_key),
        "source": source,
        "seed_batch": seed_batch,
        "notes": notes,
    }


def _observed_prompt_count(row: Any) -> int:
    try:
        return int(row.get("prompt_count", 0) or 0)
    except AttributeError:
        try:
            return int(row["prompt_count"] or 0)
        except (KeyError, TypeError, ValueError):
            return 0


def _observed_token(row: Any) -> str:
    try:
        value = row.get("token", "")
    except AttributeError:
        try:
            value = row["token"]
        except (KeyError, TypeError):
            value = ""
    return normalize_prompt_token_alias_value(str(value or ""))


def _is_noise_token(token: str) -> bool:
    if not token:
        return True
    if token in NOISE_TERMS:
        return True
    if token in NOISE_LATIN_WORDS:
        return True
    if HASHLIKE_RE.match(token):
        return True
    if token.isdigit():
        return True
    if len(token) > 18 and not any("\u4e00" <= char <= "\u9fff" for char in token):
        return True
    return False


def _is_probable_proper_name_phrase(token: str) -> bool:
    return bool(PROPER_NAME_RE.match(token))


def _valid_seed_token(token: str) -> bool:
    return _valid_manual_prompt_token(token) and (
        token in DEMOGRAPHIC_ALLOWED_TERMS or not _is_noise_token(token)
    )


def _observed_demographic_metadata(token: str) -> tuple[str, str] | None:
    if token in AGE_BASE_TERMS:
        return ("person", "age")
    if AGE_GENDER_RE.match(token):
        return ("person", "age_gender")
    if ETHNICITY_AGE_GENDER_RE.match(token):
        return ("person", "ethnicity_age_gender")
    if NUMERIC_AGE_PERSON_RE.match(token):
        return ("person", "numeric_age")
    return None


def _add_custom_term(
    terms: dict[str, PromptTokenCustomTermRule],
    term: str,
    *,
    category_key: str,
    subcategory_key: str = "",
    source: str,
    seed_batch: str,
    notes: str = "",
) -> None:
    normalized = normalize_prompt_token_alias_value(term)
    if not _valid_seed_token(normalized) or normalized in terms:
        return
    metadata = _metadata(
        category_key=category_key,
        subcategory_key=subcategory_key,
        source=source,
        seed_batch=seed_batch,
        notes=notes,
    )
    terms[normalized] = PromptTokenCustomTermRule(
        term=normalized,
        sort_order=len(terms),
        **metadata,
    )


def decompose_prompt_token(
    token: str,
    base_terms: Iterable[str],
) -> list[str]:
    normalized = normalize_prompt_token_alias_value(token)
    if not normalized:
        return []
    if not COMPACT_CJK_OR_HANGUL_KANA_RE.match(normalized):
        return []
    matches: list[tuple[int, int, str]] = []
    for term in base_terms:
        if term == normalized or len(term) < 2:
            continue
        if not COMPACT_CJK_OR_HANGUL_KANA_RE.match(term):
            continue
        start = normalized.find(term)
        if start < 0:
            continue
        matches.append((start, -len(term), term))
    if not matches:
        return []
    matches.sort()
    selected: list[str] = []
    occupied: list[range] = []
    for start, negative_len, term in matches:
        span = range(start, start + abs(negative_len))
        if any(set(span).intersection(existing) for existing in occupied):
            continue
        selected.append(term)
        occupied.append(span)
    return selected


def build_prompt_token_rule_seed_rows(
    token_rows: Iterable[Any],
    *,
    observed_custom_limit: int = PROMPT_TOKEN_RULE_OBSERVED_CUSTOM_LIMIT,
    min_observed_prompt_count: int = PROMPT_TOKEN_RULE_MIN_OBSERVED_PROMPT_COUNT,
    seed_batch: str | None = None,
) -> dict[str, Any]:
    batch = seed_batch or f"{PROMPT_TOKEN_RULE_SEED_BATCH_PREFIX}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    custom_terms: dict[str, PromptTokenCustomTermRule] = {}
    alias_rules: list[PromptTokenAliasRule] = []

    for seed in BASE_CUSTOM_TERM_SEEDS:
        _add_custom_term(
            custom_terms,
            seed.term,
            category_key=seed.category_key,
            subcategory_key=seed.subcategory_key,
            source="curated_seed",
            seed_batch=batch,
            notes=seed.notes,
        )

    alias_seen: set[str] = set()
    for seed in ALIAS_RULE_SEEDS:
        representative = normalize_prompt_token_alias_value(seed.representative)
        if not _valid_seed_token(representative):
            continue
        aliases: list[str] = []
        for raw_alias in seed.aliases:
            alias = normalize_prompt_token_alias_value(raw_alias)
            if alias == representative or not _valid_seed_token(alias):
                continue
            if alias in alias_seen:
                continue
            alias_seen.add(alias)
            aliases.append(alias)
            _add_custom_term(
                custom_terms,
                alias,
                category_key=seed.category_key,
                subcategory_key=seed.subcategory_key,
                source="curated_alias",
                seed_batch=batch,
            )
        _add_custom_term(
            custom_terms,
            representative,
            category_key=seed.category_key,
            subcategory_key=seed.subcategory_key,
            source="curated_representative",
            seed_batch=batch,
        )
        if aliases:
            metadata = _metadata(
                category_key=seed.category_key,
                subcategory_key=seed.subcategory_key,
                source="curated_alias",
                seed_batch=batch,
            )
            alias_rules.append(
                PromptTokenAliasRule(
                    representative=representative,
                    aliases=tuple(aliases),
                    sort_order=len(alias_rules),
                    category_key=metadata["category_key"],
                    category_label=metadata["category_label"],
                    subcategory_key=metadata["subcategory_key"],
                    subcategory_label=metadata["subcategory_label"],
                    source=metadata["source"],
                    seed_batch=metadata["seed_batch"],
                )
            )

    observed: list[tuple[str, int]] = []
    for row in token_rows:
        token = _observed_token(row)
        if not token:
            continue
        observed.append((token, _observed_prompt_count(row)))
    observed.sort(key=lambda item: (-item[1], item[0]))

    coverage = Counter()
    decomposition_examples: list[dict[str, Any]] = []
    noise_examples: list[str] = []
    retained_examples: list[str] = []
    base_terms = set(custom_terms)
    for token, prompt_count in observed:
        if token in base_terms:
            coverage["already_seeded"] += 1
            continue
        demographic_metadata = _observed_demographic_metadata(token)
        if (
            demographic_metadata is not None
            and prompt_count >= min_observed_prompt_count
            and _valid_seed_token(token)
        ):
            category_key, subcategory_key = demographic_metadata
            _add_custom_term(
                custom_terms,
                token,
                category_key=category_key,
                subcategory_key=subcategory_key,
                source="observed_demographic",
                seed_batch=batch,
                notes=f"observed prompt_count={prompt_count}",
            )
            base_terms.add(token)
            coverage["observed_demographic"] += 1
            continue
        if _is_noise_token(token):
            coverage["noise"] += 1
            if len(noise_examples) < 12:
                noise_examples.append(token)
            continue
        parts = decompose_prompt_token(token, base_terms)
        if parts:
            coverage["decomposed"] += 1
            if len(decomposition_examples) < 20:
                decomposition_examples.append({"token": token, "parts": parts})
            continue
        if _is_probable_proper_name_phrase(token):
            coverage["proper_name_or_entity"] += 1
            continue
        if (
            prompt_count >= min_observed_prompt_count
            and len(custom_terms) < len(BASE_CUSTOM_TERM_SEEDS) + observed_custom_limit
            and _valid_seed_token(token)
            and len(token) <= 8
        ):
            _add_custom_term(
                custom_terms,
                token,
                category_key="observed",
                subcategory_key="independent",
                source="observed_high_frequency",
                seed_batch=batch,
                notes=f"observed prompt_count={prompt_count}",
            )
            base_terms.add(token)
            coverage["observed_custom_term"] += 1
            continue
        coverage["retained_independent"] += 1
        if len(retained_examples) < 12:
            retained_examples.append(token)

    custom_rows = list(custom_terms.values())
    alias_rows = alias_rules
    return {
        "seed_batch": batch,
        "custom_terms": custom_rows,
        "alias_rules": alias_rows,
        "report": {
            "observed_token_count": len(observed),
            "custom_term_count": len(custom_rows),
            "alias_rule_count": len(alias_rows),
            "alias_token_count": sum(len(rule.aliases) for rule in alias_rows),
            "coverage": dict(coverage),
            "decomposition_examples": decomposition_examples,
            "noise_examples": noise_examples,
            "retained_examples": retained_examples,
        },
    }
