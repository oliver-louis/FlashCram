from __future__ import annotations

import base64
import html
from dataclasses import dataclass

import bleach
import markdown
from django.template.defaultfilters import striptags
from django.utils.safestring import SafeString, mark_safe


MARKDOWN_EXTENSIONS = [
    "markdown.extensions.tables",
    "pymdownx.arithmatex",
    "pymdownx.superfences",
    "pymdownx.highlight",
]
MARKDOWN_EXTENSION_CONFIGS = {
    "pymdownx.arithmatex": {
        "generic": True,
        "tex_inline_wrap": ["\\(", "\\)"],
        "tex_block_wrap": ["\\[", "\\]"],
    },
    "pymdownx.highlight": {
        "guess_lang": False,
        "pygments_lang_class": True,
    },
}
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


def render_content(text: str, content_format: str) -> SafeString:
    if content_format != "markdown":
        escaped = html.escape(text or "").replace("\n", "<br>")
        return mark_safe(escaped)

    source = text or ""
    rendered = markdown.markdown(
        source,
        extensions=MARKDOWN_EXTENSIONS,
        extension_configs=MARKDOWN_EXTENSION_CONFIGS,
        output_format="html",
    )
    cleaned = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
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
        image_data_uri=card_image_data_uri(card, face),
        image_alt=f"{card.get_image_face_display()} image",
    )


def plain_text_preview(text: str, content_format: str) -> str:
    if content_format != "markdown":
        return text or ""
    rendered = markdown.markdown(
        text or "",
        extensions=MARKDOWN_EXTENSIONS,
        extension_configs=MARKDOWN_EXTENSION_CONFIGS,
        output_format="html",
    )
    return striptags(rendered)
