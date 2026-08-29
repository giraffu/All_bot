from src.services.tg_task_result_presentation import build_result_reply_markup


def test_ref2v_result_uses_registry_gallery_capability_for_submission_button():
    markup = build_result_reply_markup(
        task_type="minimax_h3_ref2v",
        task_id="task-ref2v-audio",
        allow_contribute=True,
        reply_markup=None,
    )

    callbacks = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]
    assert "submit_gallery_task-ref2v-audio" in callbacks
