from __future__ import annotations

import json
import random
import re
from base64 import b64decode, b64encode
from io import BytesIO
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from uuid import UUID

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from PIL import Image, UnidentifiedImageError


TAG_SPLIT_RE = re.compile(r"[,\s]+")
TRAILING_HASH_TAGS_RE = re.compile(r"(?:\s+#([A-Za-z0-9_-]+))+\s*$")
HASH_TAG_RE = re.compile(r"#([A-Za-z0-9_-]+)")
REVIEW_SESSION_KEY = "review"
REVIEW_ALL_MODE = "all"
REVIEW_RANDOM_MODE = "random"
REVIEW_TAG_MODE = "tag"
REVIEW_WEAK_MODE = "weak"
REVIEW_UNSEEN_MODE = "unseen"
REVIEW_HIDDEN_MODE = "hidden"
REVIEW_MODES = {
    REVIEW_ALL_MODE: "Review all",
    REVIEW_RANDOM_MODE: "Random",
    REVIEW_TAG_MODE: "By tag",
    REVIEW_WEAK_MODE: "Weak cards",
    REVIEW_UNSEEN_MODE: "Unseen cards",
    REVIEW_HIDDEN_MODE: "Hidden cards",
}
SUMMARY_KEYS = ("reviewed", "correct", "wrong", "marked_less", "marked_hidden")
NORMAL_REVIEW_ACTIONS = {"got_it", "wrong", "show_less", "hide"}
HIDDEN_REVIEW_ACTIONS = {"restore", "keep_hidden", "skip"}
ALLOWED_IMAGE_MIMES = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
MAX_IMAGE_BYTES = 1_000_000
MAX_IMAGE_EDGE = 1600


class ImageProcessingError(ValueError):
    pass


def normalize_tags(tags: Iterable[str] | str | None) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        raw_tags = TAG_SPLIT_RE.split(tags)
    else:
        raw_tags = tags

    normalized = []
    seen = set()
    for tag in raw_tags:
        value = str(tag).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def process_image_upload(uploaded_file) -> tuple[bytes, str]:
    if not uploaded_file:
        return b"", ""
    data = uploaded_file.read()
    return process_image_bytes(data)


def process_image_bytes(data: bytes) -> tuple[bytes, str]:
    if not data:
        raise ImageProcessingError("Image file is empty.")
    try:
        image = Image.open(BytesIO(data))
        image_format = (image.format or "").upper()
    except (Image.DecompressionBombError, UnidentifiedImageError) as exc:
        raise ImageProcessingError("Unsupported image type. Use PNG, JPEG, WEBP, or GIF.") from exc

    mime = ALLOWED_IMAGE_MIMES.get(image_format)
    if not mime:
        raise ImageProcessingError("Unsupported image type. Use PNG, JPEG, WEBP, or GIF.")

    is_animated_gif = image_format == "GIF" and getattr(image, "is_animated", False)
    if is_animated_gif:
        if len(data) > MAX_IMAGE_BYTES:
            raise ImageProcessingError("Animated GIF is too large. Use an image under 1 MB.")
        return data, mime

    output = BytesIO()
    try:
        image.load()
        image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
    except Image.DecompressionBombError as exc:
        raise ImageProcessingError("Unsupported image type. Use PNG, JPEG, WEBP, or GIF.") from exc

    save_format = image_format
    save_kwargs = {}
    if image_format == "JPEG":
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        save_kwargs = {"quality": 85, "optimize": True}
    elif image_format == "PNG":
        save_kwargs = {"optimize": True}
    elif image_format == "WEBP":
        save_kwargs = {"quality": 85, "method": 6}

    image.save(output, format=save_format, **save_kwargs)
    processed = output.getvalue()
    if len(processed) > MAX_IMAGE_BYTES:
        raise ImageProcessingError("Image is too large after processing. Use an image under 1 MB.")
    return processed, mime


def image_to_base64(image_bytes) -> str | None:
    if not image_bytes:
        return None
    return b64encode(bytes(image_bytes)).decode("ascii")


def image_from_base64(value: str | None) -> bytes | None:
    if not value:
        return None
    return b64decode(value)


def is_authenticated_user(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


def get_settings(user=None):
    from .models import Settings

    if is_authenticated_user(user):
        settings, _ = Settings.objects.get_or_create(user=user)
        return settings

    legacy_settings = Settings.objects.filter(user__isnull=True).first()
    return legacy_settings or Settings()


def is_weak_card(card, settings=None) -> bool:
    settings = settings or get_settings(getattr(getattr(card, "deck", None), "owner", None))
    attempts = card.times_correct + card.times_wrong
    if attempts <= 0:
        return False
    if card.times_wrong < settings.weak_min_wrong:
        return False
    return (card.times_wrong / attempts) >= settings.weak_min_ratio


def decks_queryset(user=None, include_archived=False):
    from .models import Deck

    queryset = Deck.objects.select_related("category").all()
    if is_authenticated_user(user):
        queryset = queryset.filter(owner=user)
    if not include_archived:
        queryset = queryset.filter(is_archived=False)
    return queryset.order_by(
        "-is_pinned",
        "category__name",
        "created_at",
        "name",
    )


def archived_decks_queryset(user=None):
    return decks_queryset(user, include_archived=True).filter(is_archived=True)


def categories_queryset(user=None):
    from .models import Category

    queryset = Category.objects.all()
    if is_authenticated_user(user):
        queryset = queryset.filter(owner=user)
    return queryset.order_by("name", "created_at")


def deck_home_groups(user=None):
    decks = list(decks_queryset(user))
    categories = list(categories_queryset(user))
    has_used_categories = any(deck.category_id for deck in decks)
    pinned = [deck for deck in decks if deck.is_pinned]
    unpinned = [deck for deck in decks if not deck.is_pinned]
    category_groups = []
    uncategorized = []

    for category in categories:
        category_decks = [deck for deck in unpinned if deck.category_id == category.id]
        if category_decks:
            category_groups.append({"category": category, "decks": category_decks})

    categorized_ids = {deck.id for group in category_groups for deck in group["decks"]}
    for deck in unpinned:
        if deck.category_id is None or deck.id not in categorized_ids:
            uncategorized.append(deck)

    return {
        "pinned": pinned,
        "category_groups": category_groups,
        "uncategorized": uncategorized,
        "has_decks": bool(decks),
        "has_categories": has_used_categories,
        "show_grouped_home": bool(pinned or category_groups or has_used_categories),
    }


def cards_for_deck(deck):
    return deck.cards.all().order_by("created_at", "id")


def marked_cards_queryset(user=None):
    from .models import Card

    queryset = Card.objects.filter(is_marked=True).select_related("deck")
    if is_authenticated_user(user):
        queryset = queryset.filter(deck__owner=user)
    return queryset.order_by("deck__name", "created_at", "id")


def toggle_deck_pin(deck) -> None:
    deck.is_pinned = not deck.is_pinned
    deck.save(update_fields=["is_pinned", "updated_at"])


def toggle_deck_favorite(deck) -> None:
    deck.is_favorite = not deck.is_favorite
    deck.save(update_fields=["is_favorite", "updated_at"])


def archive_deck(deck) -> None:
    if not deck.is_archived:
        deck.is_archived = True
        deck.save(update_fields=["is_archived", "updated_at"])


def restore_deck(deck) -> None:
    if deck.is_archived:
        deck.is_archived = False
        deck.save(update_fields=["is_archived", "updated_at"])


def mark_card(card) -> None:
    if not card.is_marked:
        card.is_marked = True
        card.save(update_fields=["is_marked", "updated_at"])


def unmark_card(card) -> None:
    if card.is_marked:
        card.is_marked = False
        card.save(update_fields=["is_marked", "updated_at"])


def add_tags_to_cards(cards, tags: Iterable[str] | str) -> int:
    new_tags = normalize_tags(tags)
    if not new_tags:
        return 0

    updated = 0
    for card in cards:
        merged_tags = normalize_tags([*(card.tags or []), *new_tags])
        if merged_tags != (card.tags or []):
            card.tags = merged_tags
            card.save(update_fields=["tags", "updated_at"])
            updated += 1
    return updated


def copy_cards_to_deck(cards, deck) -> int:
    from .models import Card

    copied = 0
    for card in cards:
        Card.objects.create(
            deck=deck,
            front=card.front,
            back=card.back,
            hint=card.hint,
            content_format=card.content_format,
            tags=list(card.tags or []),
            times_reviewed=card.times_reviewed,
            times_correct=card.times_correct,
            times_wrong=card.times_wrong,
            status=card.status,
            is_marked=card.is_marked,
            image=bytes(card.image) if card.image else None,
            image_mime=card.image_mime,
            image_face=card.image_face,
        )
        copied += 1
    return copied


def filter_cards_for_deck(deck, query="", tag="", status="", marked="") -> list:
    query = (query or "").strip().lower()
    normalized_tag = normalize_tags(tag)
    selected_tag = normalized_tag[0] if normalized_tag else ""
    selected_status = (status or "").strip()
    selected_marked = (marked or "").strip()
    cards = list(cards_for_deck(deck))

    if query:
        cards = [
            card
            for card in cards
            if query in card.front.lower() or query in card.back.lower()
        ]
    if selected_tag:
        cards = [card for card in cards if selected_tag in (card.tags or [])]
    if selected_status:
        cards = [card for card in cards if card.status == selected_status]
    if selected_marked == "marked":
        cards = [card for card in cards if card.is_marked]
    elif selected_marked == "unmarked":
        cards = [card for card in cards if not card.is_marked]
    return cards


def get_deck(deck_id, user=None):
    from .models import Deck

    queryset = Deck.objects.select_related("category", "owner")
    if is_authenticated_user(user):
        queryset = queryset.filter(owner=user)
    return get_object_or_404(queryset, pk=deck_id)


def get_card_for_deck(deck, card_id, user=None):
    if is_authenticated_user(user) and deck.owner_id != user.id:
        from .models import Card

        return get_object_or_404(Card.objects.none(), pk=card_id)
    return get_object_or_404(cards_for_deck(deck), pk=card_id)


def review_all_cards(deck):
    from .models import Card

    return cards_for_deck(deck).exclude(status=Card.Status.HIDDEN)


def card_weight(card, settings=None) -> float:
    from .models import Card

    if card.status == Card.Status.HIDDEN:
        return 0.0
    if card.status == Card.Status.LESS:
        settings = settings or get_settings(getattr(getattr(card, "deck", None), "owner", None))
        return settings.show_less_weight
    return 1.0


def weighted_shuffle(cards, settings=None, rng=None) -> list:
    rng = rng or random.Random()
    weighted = []
    for card in cards:
        weight = card_weight(card, settings)
        if weight <= 0:
            continue
        weighted.append((rng.random() ** (1 / weight), card))
    weighted.sort(key=lambda item: item[0], reverse=True)
    return [card for _, card in weighted]


def cards_for_review_mode(deck, mode=REVIEW_ALL_MODE, options=None, rng=None) -> list:
    from .models import Card

    options = options or {}
    base_cards = list(cards_for_deck(deck))
    settings = get_settings(deck.owner)

    if mode == REVIEW_ALL_MODE:
        return [card for card in base_cards if card.status != Card.Status.HIDDEN]
    if mode == REVIEW_RANDOM_MODE:
        return weighted_shuffle(base_cards, settings=settings, rng=rng)
    if mode == REVIEW_TAG_MODE:
        selected_tags = set(normalize_tags(options.get("tags", [])))
        exclude_tags = bool(options.get("exclude_tags"))
        if exclude_tags:
            return [
                card
                for card in base_cards
                if card.status != Card.Status.HIDDEN and not selected_tags.intersection(card.tags or [])
            ]
        return [
            card
            for card in base_cards
            if card.status != Card.Status.HIDDEN and selected_tags.intersection(card.tags or [])
        ]
    if mode == REVIEW_WEAK_MODE:
        weak_cards = [
            card
            for card in base_cards
            if card.status != Card.Status.HIDDEN and is_weak_card(card, settings)
        ]
        return sorted(weak_cards, key=lambda card: -card.times_wrong)
    if mode == REVIEW_UNSEEN_MODE:
        return [
            card
            for card in base_cards
            if card.status != Card.Status.HIDDEN and card.times_reviewed == 0
        ]
    if mode == REVIEW_HIDDEN_MODE:
        return [card for card in base_cards if card.status == Card.Status.HIDDEN]
    raise ValueError(f"Unknown review mode: {mode}")


def empty_review_summary() -> dict[str, int]:
    return {key: 0 for key in SUMMARY_KEYS}


def start_review_session(request, deck, mode=REVIEW_ALL_MODE, options=None, rng=None) -> dict:
    options = options or {}
    queue = [str(card.id) for card in cards_for_review_mode(deck, mode, options, rng)]
    session = {
        "deck_id": str(deck.id),
        "user_id": str(request.user.id) if is_authenticated_user(request.user) else "",
        "mode": mode,
        "mode_label": "Excluding tags"
        if mode == REVIEW_TAG_MODE and options.get("exclude_tags")
        else REVIEW_MODES.get(mode, "Review"),
        "options": options,
        "queue": queue,
        "cursor": 0,
        "initial_total": len(queue),
        "log": [],
        "summary": empty_review_summary(),
    }
    request.session[REVIEW_SESSION_KEY] = session
    request.session.modified = True
    return session


def start_review_all_session(request, deck) -> dict:
    return start_review_session(request, deck, REVIEW_ALL_MODE)


def get_review_session(request) -> dict | None:
    return request.session.get(REVIEW_SESSION_KEY)


def clear_review_session(request) -> None:
    request.session.pop(REVIEW_SESSION_KEY, None)
    request.session.modified = True


def review_is_complete(session: dict) -> bool:
    return session["cursor"] >= len(session["queue"])


def review_progress(session: dict) -> tuple[int, int]:
    total = session.get("initial_total", 0)
    return min(session.get("cursor", 0), total), total


def current_review_card(session: dict):
    from .models import Card

    if review_is_complete(session):
        return None
    queryset = Card.objects.select_related("deck", "deck__owner")
    user_id = session.get("user_id")
    if user_id:
        queryset = queryset.filter(deck__owner_id=user_id)
    return get_object_or_404(queryset, pk=session["queue"][session["cursor"]])


def session_deck(session: dict):
    from .models import Deck

    queryset = Deck.objects.select_related("owner", "category")
    user_id = session.get("user_id")
    if user_id:
        queryset = queryset.filter(owner_id=user_id)
    return get_object_or_404(queryset, pk=session["deck_id"])


def apply_review_action(request, action: str) -> dict:
    from .models import Card

    if action not in NORMAL_REVIEW_ACTIONS | HIDDEN_REVIEW_ACTIONS:
        raise ValueError(f"Unknown review action: {action}")

    session = get_review_session(request)
    if not session or review_is_complete(session):
        raise ValueError("No active review card")
    if session.get("mode") == REVIEW_HIDDEN_MODE:
        return apply_hidden_review_action(request, action, session)
    if action not in NORMAL_REVIEW_ACTIONS | {"skip"}:
        raise ValueError(f"Invalid action for review mode: {action}")

    card = current_review_card(session)
    prior_cursor = session["cursor"]
    prior_queue_len = len(session["queue"])
    prior_summary = deepcopy(session["summary"])
    previous = {
        "times_reviewed": card.times_reviewed,
        "times_correct": card.times_correct,
        "times_wrong": card.times_wrong,
        "status": card.status,
    }

    summary_delta = empty_review_summary()

    if action == "got_it":
        card.times_reviewed += 1
        card.times_correct += 1
        summary_delta["reviewed"] = 1
        summary_delta["correct"] = 1
    elif action == "wrong":
        card.times_reviewed += 1
        card.times_wrong += 1
        summary_delta["reviewed"] = 1
        summary_delta["wrong"] = 1
        session["queue"].append(str(card.id))
    elif action == "show_less":
        card.times_reviewed += 1
        card.status = Card.Status.LESS
        summary_delta["reviewed"] = 1
        summary_delta["marked_less"] = 1
    elif action == "hide":
        card.times_reviewed += 1
        card.status = Card.Status.HIDDEN
        summary_delta["reviewed"] = 1
        summary_delta["marked_hidden"] = 1

    if action != "skip":
        card.save()
    for key, delta in summary_delta.items():
        session["summary"][key] += delta

    session["cursor"] += 1
    session["log"].append(
        {
            "card_id": str(card.id),
            "previous": previous,
            "prior_cursor": prior_cursor,
            "prior_queue_len": prior_queue_len,
            "prior_summary": prior_summary,
            "action": action,
        }
    )
    request.session[REVIEW_SESSION_KEY] = session
    request.session.modified = True
    return session


def apply_hidden_review_action(request, action: str, session: dict | None = None) -> dict:
    from .models import Card

    if action not in HIDDEN_REVIEW_ACTIONS:
        raise ValueError(f"Invalid hidden review action: {action}")
    session = session or get_review_session(request)
    if not session or session.get("mode") != REVIEW_HIDDEN_MODE or review_is_complete(session):
        raise ValueError("No active hidden review card")

    card = current_review_card(session)
    prior_cursor = session["cursor"]
    prior_queue_len = len(session["queue"])
    prior_summary = deepcopy(session["summary"])
    previous = {
        "times_reviewed": card.times_reviewed,
        "times_correct": card.times_correct,
        "times_wrong": card.times_wrong,
        "status": card.status,
    }

    summary_delta = empty_review_summary()
    if action == "restore":
        card.status = Card.Status.NORMAL
        card.save()
        summary_delta["reviewed"] = 1
    elif action == "keep_hidden":
        summary_delta["reviewed"] = 1

    for key, delta in summary_delta.items():
        session["summary"][key] += delta
    session["cursor"] += 1
    session["log"].append(
        {
            "card_id": str(card.id),
            "previous": previous,
            "prior_cursor": prior_cursor,
            "prior_queue_len": prior_queue_len,
            "prior_summary": prior_summary,
            "action": action,
        }
    )
    request.session[REVIEW_SESSION_KEY] = session
    request.session.modified = True
    return session


def undo_last_review_action(request) -> dict | None:
    from .models import Card

    session = get_review_session(request)
    if not session or not session.get("log"):
        return session

    entry = session["log"].pop()
    card = get_object_or_404(Card, pk=entry["card_id"])
    for field, value in entry["previous"].items():
        setattr(card, field, value)
    card.save()

    session["queue"] = session["queue"][: entry["prior_queue_len"]]
    session["cursor"] = entry["prior_cursor"]
    session["summary"] = entry["prior_summary"]
    request.session[REVIEW_SESSION_KEY] = session
    request.session.modified = True
    return session


def remove_card_from_active_review(request, card) -> dict | None:
    session = get_review_session(request)
    if not session:
        return None

    card_id = str(card.id)
    cursor = session.get("cursor", 0)
    queue = session.get("queue", [])
    prefix = queue[:cursor]
    remaining = [item for item in queue[cursor:] if item != card_id]
    session["queue"] = prefix + remaining
    session["cursor"] = min(cursor, len(session["queue"]))
    session["log"] = [
        entry for entry in session.get("log", []) if entry.get("card_id") != card_id
    ]
    request.session[REVIEW_SESSION_KEY] = session
    request.session.modified = True
    return session


@dataclass(frozen=True)
class ParsedCard:
    front: str
    back: str
    tags: list[str]
    content_format: str = ""
    hint: str = ""


@dataclass(frozen=True)
class BulkParseResult:
    cards: list[ParsedCard]
    skipped_count: int
    detected_format: str
    deck_name: str = ""
    schema: str = ""


AUTHORING_JSON_SCHEMA = "flashcram.cards.v1"


def parse_bulk_cards(text: str) -> BulkParseResult:
    text = text or ""
    content_lines = [line for line in text.splitlines() if line.strip()]
    if any(" :: " in line for line in content_lines):
        return parse_single_line_cards(content_lines)
    if any(line.strip().startswith(("Q:", "A:")) for line in content_lines):
        return parse_multiline_cards(text)
    return BulkParseResult(cards=[], skipped_count=len(content_lines), detected_format="unknown")


def parse_single_line_cards(lines: list[str]) -> BulkParseResult:
    cards = []
    skipped = 0
    for line in lines:
        if " :: " not in line:
            skipped += 1
            continue
        front, back = line.split(" :: ", 1)
        front = front.strip()
        back = back.strip()
        if not front or not back:
            skipped += 1
            continue
        tags = []
        match = TRAILING_HASH_TAGS_RE.search(back)
        if match:
            tag_text = back[match.start() :]
            tags = HASH_TAG_RE.findall(tag_text)
            back = back[: match.start()].strip()
        if not back:
            skipped += 1
            continue
        cards.append(ParsedCard(front=front, back=back, tags=normalize_tags(tags)))
    return BulkParseResult(cards=cards, skipped_count=skipped, detected_format="single-line")


def parse_multiline_cards(text: str) -> BulkParseResult:
    cards = []
    skipped = 0
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        front = ""
        back = ""
        tags = []
        for line in lines:
            if line.startswith("Q:"):
                front = line[2:].strip()
            elif line.startswith("A:"):
                back = line[2:].strip()
            elif line.startswith("Tags:"):
                tags = normalize_tags(line[5:].strip())
        if not front or not back:
            skipped += len(lines)
            continue
        cards.append(ParsedCard(front=front, back=back, tags=tags))
    return BulkParseResult(cards=cards, skipped_count=skipped, detected_format="multi-line")


def parse_authoring_json_cards(payload, user=None) -> BulkParseResult:
    from .models import Card

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8-sig")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Authoring JSON is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Authoring JSON must be an object.")
    if payload.get("version") == 1 and "decks" in payload:
        raise ValueError("This looks like a full backup JSON file. Import backups from Settings instead.")
    if payload.get("schema") != AUTHORING_JSON_SCHEMA:
        raise ValueError(f'Authoring JSON must use schema "{AUTHORING_JSON_SCHEMA}".')
    raw_cards = payload.get("cards")
    if not isinstance(raw_cards, list):
        raise ValueError('Authoring JSON must include a "cards" array.')

    settings = get_settings(user)
    default_format = settings.default_content_format
    cards = []
    skipped = 0
    for raw_card in raw_cards:
        if not isinstance(raw_card, dict):
            skipped += 1
            continue
        front = str(raw_card.get("front") or "").strip()
        back = str(raw_card.get("back") or "").strip()
        content_format = (raw_card.get("format") or raw_card.get("contentFormat") or default_format)
        hint = raw_card.get("hint")
        if hint is None:
            hint = ""
        if not isinstance(hint, str):
            skipped += 1
            continue
        hint = hint.strip()
        tags = raw_card.get("tags", [])
        if tags is None:
            tags = []
        if content_format not in {Card.ContentFormat.PLAINTEXT, Card.ContentFormat.MARKDOWN}:
            skipped += 1
            continue
        if not isinstance(tags, (list, str)):
            skipped += 1
            continue
        if not front or not back:
            skipped += 1
            continue
        cards.append(
            ParsedCard(
                front=front,
                back=back,
                hint=hint,
                tags=normalize_tags(tags),
                content_format=content_format,
            )
        )

    return BulkParseResult(
        cards=cards,
        skipped_count=skipped,
        detected_format="authoring-json",
        deck_name=str(payload.get("deck", "")).strip(),
        schema=AUTHORING_JSON_SCHEMA,
    )


def create_cards_from_parsed(deck, parsed_cards: list[ParsedCard], user=None) -> list:
    from .models import Card

    created = []
    settings = get_settings(user or deck.owner)
    valid_formats = {Card.ContentFormat.PLAINTEXT, Card.ContentFormat.MARKDOWN}
    for parsed in parsed_cards:
        content_format = parsed.content_format if parsed.content_format in valid_formats else settings.default_content_format
        created.append(
            Card.objects.create(
                deck=deck,
                front=parsed.front,
                back=parsed.back,
                hint=parsed.hint,
                content_format=content_format,
                tags=parsed.tags,
            )
        )
    return created


def isoformat(value) -> str:
    if value is None:
        return ""
    return value.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def export_backup(user=None, decks=None) -> dict:
    if decks is None and user is not None and not is_authenticated_user(user):
        decks = user
        user = None
    decks = list(decks if decks is not None else decks_queryset(user, include_archived=True))
    category_ids = {deck.category_id for deck in decks if deck.category_id}
    categories = categories_queryset(user).filter(id__in=category_ids)
    return {
        "version": 1,
        "exportedAt": isoformat(timezone.now()),
        "categories": [serialize_category(category) for category in categories],
        "decks": [serialize_deck(deck) for deck in decks],
    }


def serialize_category(category) -> dict:
    return {
        "id": str(category.id),
        "name": category.name,
        "description": category.description,
        "createdAt": isoformat(category.created_at),
        "updatedAt": isoformat(category.updated_at),
    }


def serialize_deck(deck) -> dict:
    return {
        "id": str(deck.id),
        "name": deck.name,
        "description": deck.description,
        "categoryId": str(deck.category_id) if deck.category_id else None,
        "isFavorite": deck.is_favorite,
        "isPinned": deck.is_pinned,
        "isArchived": deck.is_archived,
        "showTagsInReview": deck.show_tags_in_review,
        "createdAt": isoformat(deck.created_at),
        "updatedAt": isoformat(deck.updated_at),
        "cards": [serialize_card(card) for card in cards_for_deck(deck)],
    }


def serialize_card(card) -> dict:
    return {
        "id": str(card.id),
        "front": card.front,
        "back": card.back,
        "hint": card.hint,
        "contentFormat": card.content_format,
        "tags": card.tags or [],
        "image": image_to_base64(card.image),
        "imageMime": card.image_mime or "",
        "imageFace": card.image_face,
        "timesReviewed": card.times_reviewed,
        "timesCorrect": card.times_correct,
        "timesWrong": card.times_wrong,
        "status": card.status,
        "isMarked": card.is_marked,
        "createdAt": isoformat(card.created_at),
        "updatedAt": isoformat(card.updated_at),
    }


def parse_backup_payload(payload) -> dict:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if payload.get("version") != 1:
        raise ValueError("Unsupported backup version")
    return payload


def parse_iso_datetime(value: str):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def bool_from_backup(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def import_backup(payload, user=None) -> dict[str, int]:
    from .models import Card, Category, Deck

    data = parse_backup_payload(payload)
    counts = {"decks": 0, "cards": 0}
    category_by_id = {}

    for category_data in data.get("categories", []):
        category_id = UUID(category_data["id"])
        existing_category = Category.objects.filter(id=category_id).first()
        if existing_category and is_authenticated_user(user) and existing_category.owner_id != user.id:
            raise ValueError("Backup contains a category ID that belongs to another user.")
        category, _ = Category.objects.update_or_create(
            id=category_id,
            defaults={
                **({"owner": user} if is_authenticated_user(user) else {}),
                "name": category_data.get("name", ""),
                "description": category_data.get("description", ""),
            },
        )
        restore_timestamps(Category, category.id, category_data)
        category_by_id[str(category.id)] = category

    for deck_data in data.get("decks", []):
        deck_id = UUID(deck_data["id"])
        existing_deck = Deck.objects.filter(id=deck_id).first()
        if existing_deck and is_authenticated_user(user) and existing_deck.owner_id != user.id:
            raise ValueError("Backup contains a deck ID that belongs to another user.")
        category = None
        category_id = deck_data.get("categoryId")
        if category_id:
            category = category_by_id.get(str(category_id))
            if category is None:
                category_query = Category.objects.filter(id=category_id)
                if is_authenticated_user(user):
                    category_query = category_query.filter(owner=user)
                category = category_query.first()
        deck, _ = Deck.objects.update_or_create(
            id=deck_id,
            defaults={
                **({"owner": user} if is_authenticated_user(user) else {}),
                "name": deck_data.get("name", ""),
                "description": deck_data.get("description", ""),
                "category": category,
                "is_favorite": bool_from_backup(deck_data.get("isFavorite"), False),
                "is_pinned": bool_from_backup(deck_data.get("isPinned"), False),
                "is_archived": bool_from_backup(deck_data.get("isArchived"), False),
                "show_tags_in_review": bool_from_backup(deck_data.get("showTagsInReview"), False),
            },
        )
        restore_timestamps(Deck, deck.id, deck_data)
        counts["decks"] += 1

        for card_data in deck_data.get("cards", []):
            card_id = UUID(card_data["id"])
            existing_card = Card.objects.select_related("deck").filter(id=card_id).first()
            if existing_card and is_authenticated_user(user) and existing_card.deck.owner_id != user.id:
                raise ValueError("Backup contains a card ID that belongs to another user.")
            Card.objects.update_or_create(
                id=card_id,
                defaults={
                    "deck": deck,
                    "front": card_data.get("front", ""),
                    "back": card_data.get("back", ""),
                    "hint": card_data.get("hint") or "",
                    "content_format": card_data.get("contentFormat", Card.ContentFormat.PLAINTEXT),
                    "tags": normalize_tags(card_data.get("tags", [])),
                    "image": image_from_base64(card_data.get("image")),
                    "image_mime": card_data.get("imageMime", ""),
                    "image_face": card_data.get("imageFace", Card.ImageFace.BACK),
                    "times_reviewed": int(card_data.get("timesReviewed", 0)),
                    "times_correct": int(card_data.get("timesCorrect", 0)),
                    "times_wrong": int(card_data.get("timesWrong", 0)),
                    "status": card_data.get("status", Card.Status.NORMAL),
                    "is_marked": bool(card_data.get("isMarked", False)),
                },
            )
            restore_timestamps(Card, card_id, card_data)
            counts["cards"] += 1
    return counts


def restore_timestamps(model, object_id, data) -> None:
    updates = {}
    created_at = parse_iso_datetime(data.get("createdAt", ""))
    updated_at = parse_iso_datetime(data.get("updatedAt", ""))
    if created_at:
        updates["created_at"] = created_at
    if updated_at:
        updates["updated_at"] = updated_at
    if updates:
        model.objects.filter(pk=object_id).update(**updates)


def get_prompt_preferences(user):
    from .generation_prompts import normalize_preferences
    return normalize_preferences(get_settings(user).generation_prompt_preferences)


def save_prompt_preferences(user, preferences):
    from .generation_prompts import normalize_preferences
    settings = get_settings(user)
    settings.generation_prompt_preferences = normalize_preferences(preferences)
    settings.save(update_fields=["generation_prompt_preferences", "updated_at"])
    return settings.generation_prompt_preferences
