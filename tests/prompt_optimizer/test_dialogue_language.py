from src.prompt_optimizer.dialogue_language import (
    build_dialogue_language_contract,
    dialogue_language_contract_is_satisfied,
)


def test_dialogue_contract_detects_spoken_language_from_the_quoted_words():
    contract = build_dialogue_language_contract(
        '女人看向镜头，用英语说：“Please stay with me.” 然后轻轻呼吸。'
    )

    assert "[English]" in contract
    assert "Please stay with me." in contract
    assert "do not translate" in contract
    assert "[Chinese]" not in contract


def test_dialogue_contract_keeps_each_language_in_a_mixed_language_prompt():
    contract = build_dialogue_language_contract(
        '她低声说“不要停。”，男人 answers: "I am right here."'
    )

    assert "[Chinese]" in contract
    assert "不要停。" in contract
    assert "[English]" in contract
    assert "I am right here." in contract


def test_dialogue_contract_does_not_treat_unrelated_quoted_labels_as_speech():
    contract = build_dialogue_language_contract(
        '镜头扫过写着“OPEN”的霓虹灯，女人保持沉默。'
    )

    assert "No explicit spoken or sung line was detected" in contract
    assert "OPEN" not in contract


def test_dialogue_result_must_use_only_the_exact_source_words():
    prompt = '她说：“Please stay with me.”'

    assert dialogue_language_contract_is_satisfied(
        prompt, "(S1) says: <d>[English] Please stay with me.</d>"
    )
    assert not dialogue_language_contract_is_satisfied(
        prompt, "(S1) says: <d>[English] 请留下。 Please stay with me.</d>"
    )
