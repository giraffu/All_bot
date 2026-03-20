import pytest
from src.constants import get_resolution_keyboard, DEFAULT_RESOLUTION, RESOLUTION_PERMISSIONS, RESOLUTION_COST

def test_resolution_keyboard_length_and_content():
    # 测试凡人 + default identity (外门弟子)
    kb_mortal = get_resolution_keyboard("凡人")
    assert len(kb_mortal.inline_keyboard) == 1
    assert len(kb_mortal.inline_keyboard[0]) == 1
    assert kb_mortal.inline_keyboard[0][0].text == "✅ 512p"
    assert kb_mortal.inline_keyboard[0][0].callback_data == "set_res_512p"

    # 测试筑基期
    kb_zhuji = get_resolution_keyboard("筑基期")
    assert len(kb_zhuji.inline_keyboard) == 1
    assert len(kb_zhuji.inline_keyboard[0]) == 2
    texts = [btn.text for btn in kb_zhuji.inline_keyboard[0]]
    assert "✅ 512p" in texts
    assert "720p" in texts

    # 测试金丹期
    kb_jindan = get_resolution_keyboard("金丹期")
    assert len(kb_jindan.inline_keyboard) == 1
    assert len(kb_jindan.inline_keyboard[0]) == 3
    texts = [btn.text for btn in kb_jindan.inline_keyboard[0]]
    assert "✅ 512p" in texts
    assert "720p" in texts
    assert "1024p" in texts

    # Mortal with Inner Disciple Identity (内门弟子)
    kb_vip = get_resolution_keyboard("凡人", "内门弟子")
    assert len(kb_vip.inline_keyboard) == 1
    assert len(kb_vip.inline_keyboard[0]) == 3
    assert kb_vip.inline_keyboard[0][2].callback_data == "set_res_1024p"

def test_default_resolution_constant():
    assert DEFAULT_RESOLUTION == "512p"

def test_toast_message_formatting():
    # Simulate toast message logic
    for res in ["512p", "720p", "1024p"]:
        cost = RESOLUTION_COST.get(res)
        toast_msg = f"已切换至 {res}，灵石消耗 {cost}"
        
        if res == "512p":
            assert toast_msg == "已切换至 512p，灵石消耗 6"
        elif res == "720p":
            assert toast_msg == "已切换至 720p，灵石消耗 10"
        elif res == "1024p":
            assert toast_msg == "已切换至 1024p，灵石消耗 20"
