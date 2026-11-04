from __future__ import annotations

import base64
import html
import re
import uuid
from dataclasses import dataclass

import bleach
import markdown

from .diagrams import mermaid_fence, summary_fence
from django.template.defaultfilters import striptags
from django.utils.safestring import SafeString, mark_safe


MARKDOWN_EXTENSIONS = [
    "markdown.extensions.tables",
    "pymdownx.arithmatex",
    "pymdownx.superfences",
    "pymdownx.highlight",
]
MARKDOWN_EXTENSION_CONFIGS = {
    "pymdownx.superfences": {"custom_fences": [{"name": "mermaid", "class": "mermaid", "format": mermaid_fence}]},
    "pymdownx.arithmatex": {
        "generic": True,
        "inline_syntax": ["round"],
        "block_syntax": ["dollar", "square"],
        "tex_inline_wrap": ["\\(", "\\)"],
        "tex_block_wrap": ["\\[", "\\]"],
    },
    "pymdownx.highlight": {
        "guess_lang": False,
        "pygments_lang_class": True,
    },
}
MATH_PREVIEW_PATTERNS = [
    re.compile(r"\\\((.*?)\\\)", re.DOTALL),
    re.compile(r"\\\[(.*?)\\\]", re.DOTALL),
    re.compile(r"\$\$(.*?)\$\$", re.DOTALL),
]
DISPLAY_MATH_OPENERS = {"\\["}
DISPLAY_MATH_CLOSERS = {"\\]"}
ALLOWED_TAGS = [
    "a",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "code": ["class"],
    "div": ["class"],
    "pre": ["class"],
    "span": ["class"],
    "table": ["class"],
}


@dataclass(frozen=True)
class RenderedFace:
    html: SafeString
    image_data_uri: str
    image_alt: str
    enable_math: bool = False
    hint_html: SafeString = ""


def normalize_display_math_blocks(source: str) -> str:
    """Give standalone display math delimiters paragraph spacing for Markdown."""
    lines = (source or "").splitlines()
    if not lines:
        return source or ""

    normalized: list[str] = []
    in_fence = False
    in_dollar_math = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence

        is_square_opener = not in_fence and stripped in DISPLAY_MATH_OPENERS
        is_square_closer = not in_fence and stripped in DISPLAY_MATH_CLOSERS
        is_dollar_delimiter = not in_fence and stripped == "$$"
        is_opener = is_square_opener or (is_dollar_delimiter and not in_dollar_math)
        is_closer = is_square_closer or (is_dollar_delimiter and in_dollar_math)

        if is_opener and normalized and normalized[-1].strip():
            normalized.append("")

        normalized.append(line)

        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if is_closer and next_line.strip():
            normalized.append("")
        if is_dollar_delimiter:
            in_dollar_math = not in_dollar_math

    trailing_newline = "\n" if (source or "").endswith("\n") else ""
    return "\n".join(normalized) + trailing_newline


def render_content(text: str, content_format: str) -> SafeString:
    if content_format != "markdown":
        escaped = html.escape(text or "").replace("\n", "<br>")
        return mark_safe(escaped)

    source = normalize_display_math_blocks(text or "")
    diagrams = {}

    def validated_fence(source, language, class_name, options, md, **kwargs):
        token = 'FCMERMAID' + uuid.uuid4().hex
        diagrams[token] = mermaid_fence(source, language, class_name, options, md, **kwargs)
        return f'<p>{token}</p>'

    rendered = markdown.markdown(
        source,
        extensions=MARKDOWN_EXTENSIONS,
        extension_configs={**MARKDOWN_EXTENSION_CONFIGS, "pymdownx.superfences": {"custom_fences": [{"name": "mermaid", "class": "mermaid", "format": validated_fence}]}},
        output_format="html",
    )
    cleaned = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
    for token, diagram in diagrams.items():
        cleaned = cleaned.replace(f"<p>{token}</p>", diagram)
    return mark_safe(cleaned)


def card_image_data_uri(card, face: str) -> str:
    if not card or not card.image or card.image_face != face or not card.image_mime:
        return ""
    image_bytes = bytes(card.image)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{card.image_mime};base64,{encoded}"


def render_card_face(card, face: str) -> RenderedFace:
    text = card.front if face == "front" else card.back
    return RenderedFace(
        html=render_content(text, card.content_format),
        hint_html=render_content(card.hint, card.content_format) if face == "front" and card.hint.strip() else "",
        image_data_uri=card_image_data_uri(card, face),
        image_alt=f"{card.get_image_face_display()} image",
        enable_math=card.content_format == "markdown",
    )


def strip_math_delimiters(text: str) -> str:
    value = text or ""
    for pattern in MATH_PREVIEW_PATTERNS:
        value = pattern.sub(lambda match: match.group(1), value)
    return re.sub(r"\s+", " ", value).strip()


def plain_text_preview(text: str, content_format: str) -> str:
    if content_format != "markdown":
        return text or ""
    source = normalize_display_math_blocks(text or "")
    rendered = markdown.markdown(
        source,
        extensions=MARKDOWN_EXTENSIONS,
        extension_configs={**MARKDOWN_EXTENSION_CONFIGS, "pymdownx.superfences": {"custom_fences": [{"name": "mermaid", "class": "mermaid", "format": summary_fence}]}},
        output_format="html",
    )
    return strip_math_delimiters(striptags(rendered))
