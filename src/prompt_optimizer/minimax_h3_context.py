from __future__ import annotations

from typing import Any

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_ADDON_MODELS,
    MiniMaxH3ValidationError,
    normalize_minimax_h3_addon_items,
)


def build_minimax_h3_addon_prompt_context(
    raw_items: list[dict[str, Any]],
) -> dict[str, Any]:
    selections = normalize_minimax_h3_addon_items(raw_items)
    addon_ids = [item.name for item in selections]
    if selections:
        summary = "\n".join(
            f"- {MINIMAX_H3_ADDON_MODELS[item.name].label_en} "
            f"(strength {item.strength:g})"
            for item in selections
        )
        rules = "\n".join(
            f"- {MINIMAX_H3_ADDON_MODELS[item.name].label_en}: "
            f"{MINIMAX_H3_ADDON_MODELS[item.name].prompt_guide_en}"
            for item in selections
        )
    else:
        summary = "None selected."
        rules = "No add-on-specific prompt guidance."
    breasts_selected = "breasts" in addon_ids
    return {
        "addon_ids": addon_ids,
        "addon_summary": summary,
        "addon_rules": rules,
        "breasts_vocabulary_rule": (
            "The breast add-on is selected. When visual evidence or the original request "
            "supports it, describe nipples and areoles; always spell areoles this way, "
            "never areolas."
            if breasts_selected
            else "The breast add-on is not selected. nipples and areoles remain forbidden."
        ),
    }


__all__ = [
    "MiniMaxH3ValidationError",
    "build_minimax_h3_addon_prompt_context",
]
