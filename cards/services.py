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
HIDDEN_REVIEW_ACTIONS = {"restore", "keep_hidden"}
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


def get_settings():
    from .models import Settings

    settings, _ = Settings.objects.get_or_create(pk=Settings.SINGLETON_PK)
    return settings


def is_weak_card(card, settings=None) -> bool:
    settings = settings or get_settings()
    attempts = card.times_correct + card.times_wrong
    if attempts <= 0:
        return False
    if card.times_wrong < settings.weak_min_wrong:
        return False
    return (card.times_wrong / attempts) >= settings.weak_min_ratio


def decks_queryset():
    from .models import Deck

    return Deck.objects.all().order_by("created_at", "name")


def cards_for_deck(deck):
    return deck.cards.all().order_by("created_at", "id")


def filter_cards_for_deck(deck, query="", tag="") -> list:
    query = (query or "").strip().lower()
    normalized_tag = normalize_tags(tag)
    selected_tag = normalized_tag[0] if normalized_tag else ""
    cards = list(cards_for_deck(deck))

    if query:
        cards = [
            card
            for card in cards
            if query in card.front.lower() or query in card.back.lower()
        ]
    if selected_tag:
        cards = [card for card in cards if selected_tag in (card.tags or [])]
    return cards


def get_deck(deck_id):
    from .models import Deck

    return get_object_or_404(Deck, pk=deck_id)


def get_card_for_deck(deck, card_id):
    return get_object_or_404(cards_for_deck(deck), pk=card_id)


def review_all_cards(deck):
    from .models import Card

    return cards_for_deck(deck).exclude(status=Card.Status.HIDDEN)


def card_weight(card, settings=None) -> float:
    from .models import Card

    if card.status == Card.Status.HIDDEN:
        return 0.0
    if card.status == Card.Status.LESS:
        settings = settings or get_settings()
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
    settings = get_settings()

    if mode == REVIEW_ALL_MODE:
        return [card for card in base_cards if card.status != Card.Status.HIDDEN]
    if mode == REVIEW_RANDOM_MODE:
        return weighted_shuffle(base_cards, settings=settings, rng=rng)
    if mode == REVIEW_TAG_MODE:
        selected_tags = set(normalize_tags(options.get("tags", [])))
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
        "mode": mode,
        "mode_label": REVIEW_MODES.get(mode, "Review"),
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
    return get_object_or_404(Card, pk=session["queue"][session["cursor"]])


def session_deck(session: dict):
    from .models import Deck

    return get_object_or_404(Deck, pk=session["deck_id"])


def apply_review_action(request, action: str) -> dict:
    from .models import Card

    if action not in NORMAL_REVIEW_ACTIONS | HIDDEN_REVIEW_ACTIONS:
        raise ValueError(f"Unknown review action: {action}")

    session = get_review_session(request)
    if not session or review_is_complete(session):
        raise ValueError("No active review card")
    if session.get("mode") == REVIEW_HIDDEN_MODE:
        return apply_hidden_review_action(request, action, session)
    if action not in NORMAL_REVIEW_ACTIONS:
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
    card.times_reviewed += 1
    summary_delta["reviewed"] = 1

    if action == "got_it":
        card.times_correct += 1
        summary_delta["correct"] = 1
    elif action == "wrong":
        card.times_wrong += 1
        summary_delta["wrong"] = 1
        session["queue"].append(str(card.id))
    elif action == "show_less":
        card.status = Card.Status.LESS
        summary_delta["marked_less"] = 1
    elif action == "hide":
        card.status = Card.Status.HIDDEN
        summary_delta["marked_hidden"] = 1

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
    summary_delta["reviewed"] = 1
    if action == "restore":
        card.status = Card.Status.NORMAL
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


@dataclass(frozen=True)
class ParsedCard:
    front: str
    back: str
    tags: list[str]
    content_format: str = ""


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


def parse_authoring_json_cards(payload) -> BulkParseResult:
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

    settings = get_settings()
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


def create_cards_from_parsed(deck, parsed_cards: list[ParsedCard]) -> list:
    from .models import Card

    created = []
    settings = get_settings()
    valid_formats = {Card.ContentFormat.PLAINTEXT, Card.ContentFormat.MARKDOWN}
    for parsed in parsed_cards:
        content_format = parsed.content_format if parsed.content_format in valid_formats else settings.default_content_format
        created.append(
            Card.objects.create(
                deck=deck,
                front=parsed.front,
                back=parsed.back,
                content_format=content_format,
                tags=parsed.tags,
            )
        )
    return created


def isoformat(value) -> str:
    if value is None:
        return ""
    return value.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def export_backup(decks=None) -> dict:
    decks = decks if decks is not None else decks_queryset()
    return {
        "version": 1,
        "exportedAt": isoformat(timezone.now()),
        "decks": [serialize_deck(deck) for deck in decks],
    }


def serialize_deck(deck) -> dict:
    return {
        "id": str(deck.id),
        "name": deck.name,
        "description": deck.description,
        "createdAt": isoformat(deck.created_at),
        "updatedAt": isoformat(deck.updated_at),
        "cards": [serialize_card(card) for card in cards_for_deck(deck)],
    }


def serialize_card(card) -> dict:
    return {
        "id": str(card.id),
        "front": card.front,
        "back": card.back,
        "contentFormat": card.content_format,
        "tags": card.tags or [],
        "image": image_to_base64(card.image),
        "imageMime": card.image_mime or "",
        "imageFace": card.image_face,
        "timesReviewed": card.times_reviewed,
        "timesCorrect": card.times_correct,
        "timesWrong": card.times_wrong,
        "status": card.status,
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


def import_backup(payload) -> dict[str, int]:
    from .models import Card, Deck

    data = parse_backup_payload(payload)
    counts = {"decks": 0, "cards": 0}
    for deck_data in data.get("decks", []):
        deck_id = UUID(deck_data["id"])
        deck, _ = Deck.objects.update_or_create(
            id=deck_id,
            defaults={
                "name": deck_data.get("name", ""),
                "description": deck_data.get("description", ""),
            },
        )
        restore_timestamps(Deck, deck.id, deck_data)
        counts["decks"] += 1

        for card_data in deck_data.get("cards", []):
            card_id = UUID(card_data["id"])
            Card.objects.update_or_create(
                id=card_id,
                defaults={
                    "deck": deck,
                    "front": card_data.get("front", ""),
                    "back": card_data.get("back", ""),
                    "content_format": card_data.get("contentFormat", Card.ContentFormat.PLAINTEXT),
                    "tags": normalize_tags(card_data.get("tags", [])),
                    "image": image_from_base64(card_data.get("image")),
                    "image_mime": card_data.get("imageMime", ""),
                    "image_face": card_data.get("imageFace", Card.ImageFace.BACK),
                    "times_reviewed": int(card_data.get("timesReviewed", 0)),
                    "times_correct": int(card_data.get("timesCorrect", 0)),
                    "times_wrong": int(card_data.get("timesWrong", 0)),
                    "status": card_data.get("status", Card.Status.NORMAL),
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
