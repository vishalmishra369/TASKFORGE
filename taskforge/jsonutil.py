"""Tolerant JSON / code-block extraction from LLM text."""
from __future__ import annotations

import json
import re


def extract_json(text: str):
    """Parse the first JSON object/array in text (handles ``` fences and chatter)."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s, e = t.find(open_c), t.rfind(close_c)
        if s != -1 and e > s:
            try:
                return json.loads(t[s : e + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no valid JSON found in model output")


def extract_code(text: str, lang: str = "python") -> str:
    m = re.search(rf"```{lang}\s*(.*?)```", text, re.S) or re.search(r"```\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"
