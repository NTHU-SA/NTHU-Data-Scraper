"""Shared whitespace and control-character normalization for dataset text."""

import re


def normalize_single_line_text(text: str) -> str:
    return " ".join(re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text).split())


def normalize_multiline_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = (normalize_single_line_text(line) for line in text.split("\n"))
    return "\n".join(line for line in lines if line)
