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
    assert "h3_extend:task-ref2v-audio" in callbacks


def test_second_h3_segment_offers_free_stitch_and_extension():
    markup = build_result_reply_markup(
        task_type="minimax_h3_i2v",
        task_id="task-h3-2",
        allow_contribute=True,
        reply_markup=None,
        result_meta={
            "minimax_h3_prev_task_id": "task-h3-1",
            "minimax_h3_chain_task_ids": ["task-h3-1"],
        },
    )

    callbacks = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]
    assert "h3_extend:task-h3-2" in callbacks
    assert "h3_stitch:task-h3-2" in callbacks


def test_h3_t2v_and_stitched_results_do_not_offer_extension():
    for task_type, result_meta in (
        ("minimax_h3_t2v", {}),
        ("minimax_h3_i2v", {"minimax_h3_is_stitched": True}),
    ):
        markup = build_result_reply_markup(
            task_type=task_type,
            task_id="task-h3",
            allow_contribute=False,
            reply_markup=None,
            result_meta=result_meta,
        )
        callbacks = [
            button.callback_data for row in markup.inline_keyboard for button in row
        ]
        assert not any(str(value).startswith("h3_extend:") for value in callbacks)
