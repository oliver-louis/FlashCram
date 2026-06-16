from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import CardForm, DeckForm
from .services import (
    apply_review_action,
    cards_for_deck,
    clear_review_session,
    current_review_card,
    decks_queryset,
    get_card_for_deck,
    get_deck,
    review_is_complete,
    review_progress,
    session_deck,
    start_review_all_session,
    undo_last_review_action,
)


def htmx_redirect(to):
    response = HttpResponse(status=204)
    response["HX-Redirect"] = to
    return response


def home(request):
    return render(request, "cards/home.html", {"decks": decks_queryset()})


def deck_detail(request, deck_id):
    deck = get_deck(deck_id)
    return render(
        request,
        "cards/deck_detail.html",
        {"deck": deck, "cards": cards_for_deck(deck)},
    )


def deck_create(request):
    if request.method == "POST":
        form = DeckForm(request.POST)
        if form.is_valid():
            deck = form.save()
            if request.htmx:
                return render(
                    request,
                    "cards/partials/deck_create_success.html",
                    {"deck": deck},
                    status=201,
                )
            return redirect("cards:deck_detail", deck_id=deck.id)
    else:
        form = DeckForm()

    template = "cards/partials/deck_form.html" if request.htmx else "cards/deck_form_page.html"
    return render(
        request,
        template,
        {
            "form": form,
            "title": "New deck",
            "submit_label": "Create deck",
            "action_url": reverse("cards:deck_create"),
        },
        status=422 if request.method == "POST" else 200,
    )


def deck_edit(request, deck_id):
    deck = get_deck(deck_id)
    if request.method == "POST":
        form = DeckForm(request.POST, instance=deck)
        if form.is_valid():
            deck = form.save()
            if request.htmx:
                return render(request, "cards/partials/deck_header.html", {"deck": deck})
            return redirect("cards:deck_detail", deck_id=deck.id)
    else:
        form = DeckForm(instance=deck)

    template = "cards/partials/deck_form.html" if request.htmx else "cards/deck_form_page.html"
    return render(
        request,
        template,
        {
            "form": form,
            "deck": deck,
            "title": "Edit deck",
            "submit_label": "Save deck",
            "action_url": reverse("cards:deck_edit", kwargs={"deck_id": deck.id}),
        },
        status=422 if request.method == "POST" else 200,
    )


@require_POST
def deck_delete(request, deck_id):
    deck = get_deck(deck_id)
    deck.delete()
    if request.htmx:
        return htmx_redirect(reverse("cards:home"))
    return redirect("cards:home")


def card_create(request, deck_id):
    deck = get_deck(deck_id)
    if request.method == "POST":
        form = CardForm(request.POST)
        if form.is_valid():
            card = form.save(commit=False)
            card.deck = deck
            card.save()
            if request.htmx:
                return render(
                    request,
                    "cards/partials/card_create_success.html",
                    {"deck": deck, "card": card},
                    status=201,
                )
            return redirect("cards:deck_detail", deck_id=deck.id)
    else:
        form = CardForm()

    template = "cards/partials/card_form.html" if request.htmx else "cards/card_form_page.html"
    return render(
        request,
        template,
        {
            "form": form,
            "deck": deck,
            "title": "Add card",
            "submit_label": "Create card",
            "action_url": reverse("cards:card_create", kwargs={"deck_id": deck.id}),
        },
        status=422 if request.method == "POST" else 200,
    )


def card_edit(request, deck_id, card_id):
    deck = get_deck(deck_id)
    card = get_card_for_deck(deck, card_id)
    if request.method == "POST":
        form = CardForm(request.POST, instance=card)
        if form.is_valid():
            card = form.save()
            if request.htmx:
                return render(request, "cards/partials/card_row.html", {"deck": deck, "card": card})
            return redirect("cards:deck_detail", deck_id=deck.id)
    else:
        form = CardForm(instance=card)

    template = "cards/partials/card_form.html" if request.htmx else "cards/card_form_page.html"
    return render(
        request,
        template,
        {
            "form": form,
            "deck": deck,
            "card": card,
            "title": "Edit card",
            "submit_label": "Save card",
            "action_url": reverse(
                "cards:card_edit", kwargs={"deck_id": deck.id, "card_id": card.id}
            ),
        },
        status=422 if request.method == "POST" else 200,
    )


@require_POST
def card_delete(request, deck_id, card_id):
    deck = get_deck(deck_id)
    card = get_card_for_deck(deck, card_id)
    card.delete()
    if request.htmx:
        return HttpResponse("")
    return redirect("cards:deck_detail", deck_id=deck.id)


def review_start(request, deck_id):
    deck = get_deck(deck_id)
    session = start_review_all_session(request, deck)
    if review_is_complete(session):
        summary = session["summary"].copy()
        clear_review_session(request)
        return render(request, "cards/review.html", {"deck": deck, "summary": summary})

    return render(
        request,
        "cards/review.html",
        review_context(session),
    )


@require_POST
def review_grade(request, action):
    try:
        session = apply_review_action(request, action)
    except ValueError:
        return htmx_redirect(reverse("cards:home"))

    deck = session_deck(session)
    if review_is_complete(session):
        summary = session["summary"].copy()
        clear_review_session(request)
        return render(
            request,
            "cards/partials/review_summary.html",
            {"deck": deck, "summary": summary},
        )

    return render(request, "cards/partials/review_card.html", review_context(session))


@require_POST
def review_undo(request):
    session = undo_last_review_action(request)
    if not session:
        return htmx_redirect(reverse("cards:home"))
    return render(request, "cards/partials/review_card.html", review_context(session))


def review_context(session):
    deck = session_deck(session)
    card = current_review_card(session)
    progress_current, progress_total = review_progress(session)
    return {
        "deck": deck,
        "card": card,
        "session": session,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "can_undo": bool(session.get("log")),
    }
