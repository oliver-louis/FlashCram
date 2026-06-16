import json

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import BulkImportForm, CardForm, DeckForm, JsonImportForm, SettingsForm
from .models import Deck
from .services import (
    REVIEW_ALL_MODE,
    REVIEW_HIDDEN_MODE,
    apply_review_action,
    cards_for_deck,
    clear_review_session,
    create_cards_from_parsed,
    current_review_card,
    decks_queryset,
    export_backup,
    get_card_for_deck,
    get_deck,
    get_settings,
    import_backup,
    parse_bulk_cards,
    review_is_complete,
    review_progress,
    session_deck,
    start_review_session,
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
    return review_start_mode(request, deck_id, REVIEW_ALL_MODE)


def review_start_mode(request, deck_id, mode):
    deck = get_deck(deck_id)
    session = start_review_session(request, deck, mode)
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
def review_start_tag(request, deck_id):
    deck = get_deck(deck_id)
    tags = request.POST.getlist("tags")
    session = start_review_session(request, deck, "tag", {"tags": tags})
    if review_is_complete(session):
        summary = session["summary"].copy()
        clear_review_session(request)
        return render(request, "cards/review.html", {"deck": deck, "summary": summary})
    return render(request, "cards/review.html", review_context(session))


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
        "is_hidden_mode": session.get("mode") == REVIEW_HIDDEN_MODE,
    }


def bulk_import(request):
    result = None
    created_count = None
    form = BulkImportForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        result = parse_bulk_cards(form.cleaned_data["text"])
        if request.POST.get("intent") == "confirm":
            deck = form.cleaned_data["deck"]
            if deck is None:
                deck = Deck.objects.create(name=form.cleaned_data["new_deck_name"])
            create_cards_from_parsed(deck, result.cards)
            created_count = len(result.cards)
            return redirect("cards:deck_detail", deck_id=deck.id)

    return render(
        request,
        "cards/bulk_import.html",
        {
            "form": form,
            "result": result,
            "created_count": created_count,
        },
    )


def settings_view(request):
    settings = get_settings()
    settings_form = SettingsForm(instance=settings)
    import_form = JsonImportForm()
    import_result = None

    if request.method == "POST":
        if request.POST.get("form") == "settings":
            settings_form = SettingsForm(request.POST, instance=settings)
            if settings_form.is_valid():
                settings_form.save()
                return redirect("cards:settings")
        elif request.POST.get("form") == "json_import":
            import_form = JsonImportForm(request.POST)
            if import_form.is_valid():
                import_result = import_backup(import_form.cleaned_data["backup_json"])

    return render(
        request,
        "cards/settings.html",
        {
            "settings_form": settings_form,
            "import_form": import_form,
            "import_result": import_result,
        },
    )


def export_all(request):
    payload = export_backup()
    return json_response(payload, "flashcram-backup.json")


def export_deck(request, deck_id):
    deck = get_deck(deck_id)
    payload = export_backup([deck])
    return json_response(payload, f"flashcram-{deck.id}.json")


def json_response(payload, filename):
    response = HttpResponse(
        json.dumps(payload, indent=2),
        content_type="application/json",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
