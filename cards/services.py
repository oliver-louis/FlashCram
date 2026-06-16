from __future__ import annotations

import re
from collections.abc import Iterable
from copy import deepcopy

from django.shortcuts import get_object_or_404


TAG_SPLIT_RE = re.compile(r"[,\s]+")
REVIEW_SESSION_KEY = "review"
REVIEW_ALL_MODE = "all"
SUMMARY_KEYS = ("reviewed", "correct", "wrong", "marked_less", "marked_hidden")


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


def get_deck(deck_id):
    from .models import Deck

    return get_object_or_404(Deck, pk=deck_id)


def get_card_for_deck(deck, card_id):
    return get_object_or_404(cards_for_deck(deck), pk=card_id)


def review_all_cards(deck):
    from .models import Card

    return cards_for_deck(deck).exclude(status=Card.Status.HIDDEN)


def empty_review_summary() -> dict[str, int]:
    return {key: 0 for key in SUMMARY_KEYS}


def start_review_all_session(request, deck) -> dict:
    queue = [str(card.id) for card in review_all_cards(deck)]
    session = {
        "deck_id": str(deck.id),
        "mode": REVIEW_ALL_MODE,
        "queue": queue,
        "cursor": 0,
        "initial_total": len(queue),
        "log": [],
        "summary": empty_review_summary(),
    }
    request.session[REVIEW_SESSION_KEY] = session
    request.session.modified = True
    return session


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

    if action not in {"got_it", "wrong", "show_less", "hide"}:
        raise ValueError(f"Unknown review action: {action}")

    session = get_review_session(request)
    if not session or review_is_complete(session):
        raise ValueError("No active review card")

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
