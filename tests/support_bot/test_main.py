from support_bot.main import CATEGORY_BY_TEXT, WELCOME


def test_support_start_copy_includes_recharge_evidence_guidance():
    assert "付款截图" in WELCOME
    assert "套餐" in WELCOME
    assert "Bot Token" in WELCOME


def test_support_category_buttons_map_to_persisted_categories():
    assert CATEGORY_BY_TEXT == {
        "充值问题": "recharge",
        "Bug反馈": "bug",
        "意见反馈": "suggestion",
    }
