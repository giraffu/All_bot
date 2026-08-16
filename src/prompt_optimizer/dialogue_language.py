from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DialogueAnchor:
    text: str
    language: str


_SPEECH_MARKER = (
    r"(?:低声说|轻声说|大声说|说道|说着|说|喊道|喊|问道|问|回答|耳语|叫道|唱道|唱|"
    r"对白|台词|\b(?:says?|said|answers?|asks?|whispers?|shouts?|yells?|sings?|"
    r"speaks?|dialogue|line)\b)"
)
_QUOTED_SPEECH = re.compile(
    _SPEECH_MARKER
    + r"[^\n“”\"']{0,16}(?:“(?P<curly>[^”\n]{1,500})”|\"(?P<double>[^\"\n]{1,500})\"|'(?P<single>[^'\n]{1,500})')",
    flags=re.IGNORECASE,
)
_TAGGED_DIALOGUE = re.compile(
    r"<d>\s*\[[^\]]+\]\s*(?P<text>[^<]{1,500})</d>",
    flags=re.IGNORECASE,
)


def detect_dialogue_language(text: str) -> str:
    if re.search(r"[\u3040-\u30ff]", text):
        return "Japanese"
    if re.search(r"[\uac00-\ud7af]", text):
        return "Korean"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "Chinese"
    if re.search(r"[\u0400-\u04ff]", text):
        return "Russian"
    if re.search(r"[\u0600-\u06ff]", text):
        return "Arabic"
    if re.search(r"[\u0900-\u097f]", text):
        return "Hindi"
    if re.search(r"[\u0e00-\u0e7f]", text):
        return "Thai"
    return "English"


def extract_dialogue_anchors(prompt: str) -> tuple[DialogueAnchor, ...]:
    candidates: list[str] = []
    for match in _TAGGED_DIALOGUE.finditer(str(prompt)):
        candidates.append(match.group("text"))
    for match in _QUOTED_SPEECH.finditer(str(prompt)):
        candidates.append(
            match.group("curly") or match.group("double") or match.group("single")
        )

    anchors: list[DialogueAnchor] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = candidate.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        anchors.append(DialogueAnchor(text=text, language=detect_dialogue_language(text)))
    return tuple(anchors)


def build_dialogue_language_contract(prompt: str) -> str:
    anchors = extract_dialogue_anchors(prompt)
    if not anchors:
        return (
            "No explicit spoken or sung line was detected. Do not invent dialogue. "
            "If the request contains clearly unquoted speech, infer its language from "
            "the spoken words themselves and do not translate it."
        )
    lines = [
        "Server-detected dialogue language contract. Narrative language does not override "
        "the language of the quoted spoken words:"
    ]
    lines.extend(
        f"- Dialogue {index}: use [{anchor.language}] and preserve this exact source "
        f"text verbatim; do not translate: {anchor.text}"
        for index, anchor in enumerate(anchors, start=1)
    )
    return "\n".join(lines)


def dialogue_language_contract_is_satisfied(prompt: str, result_text: str) -> bool:
    for anchor in extract_dialogue_anchors(prompt):
        tagged_values = re.findall(
            rf"<d>\s*\[{re.escape(anchor.language)}\]\s*(?P<text>[^<]*)</d>",
            result_text,
            flags=re.IGNORECASE,
        )
        allowed_values = {anchor.text}
        if not re.search(r"[.!?。！？]$", anchor.text):
            allowed_values.update(anchor.text + punctuation for punctuation in ".!?。！？")
        if not any(value.strip() in allowed_values for value in tagged_values):
            return False
    return True
