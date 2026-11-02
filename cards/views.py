import json

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import BulkImportForm, CardDraftPreviewForm, CardForm, DeckCreateForm, DeckForm, JsonImportForm, SettingsForm
from .models import Card, Deck
from .rendering import RenderedFace, render_card_face, render_content
from .services import (
    REVIEW_ALL_MODE,
    REVIEW_HIDDEN_MODE,
    add_tags_to_cards,
    archive_deck,
    archived_decks_queryset,
    apply_review_action,
    cards_for_deck,
    categories_queryset,
    clear_review_session,
    copy_cards_to_deck,
    create_cards_from_parsed,
    current_review_card,
    deck_home_groups,
    decks_queryset,
    export_backup,
    filter_cards_for_deck,
    get_card_for_deck,
    get_deck,
    get_review_session,
    get_settings,
    import_backup,
    mark_card,
    marked_cards_queryset,
    parse_authoring_json_cards,
    parse_bulk_cards,
    remove_card_from_active_review,
    restore_deck,
    review_is_complete,
    review_progress,
    session_deck,
    start_review_session,
    toggle_deck_favorite,
    toggle_deck_pin,
    unmark_card,
    undo_last_review_action,
)


def htmx_redirect(to):
    response = HttpResponse(status=204)
    response["HX-Redirect"] = to
    return response


def populate_uploaded_json_text(post_data, files, file_field, text_field):
    if post_data is None or post_data.get(text_field) or not files.get(file_field):
        return post_data
    try:
        post_data[text_field] = files[file_field].read().decode("utf-8-sig")
    except UnicodeDecodeError:
        post_data[text_field] = ""
    return post_data


def home(request):
    groups = deck_home_groups(request.user)
    return render(
        request,
        "cards/home.html",
        groups,
    )


def archived_decks(request):
    return render(
        request,
        "cards/archived_decks.html",
        {"decks": archived_decks_queryset(request.user)},
    )


def deck_review_cards(deck):
    return [
        {"id": str(card.id), "tags": card.tags or []}
        for card in cards_for_deck(deck)
        if card.status != Card.Status.HIDDEN
    ]


def deck_detail(request, deck_id):
    deck = get_deck(deck_id, request.user)
    return render(
        request,
        "cards/deck_detail.html",
        {
            "deck": deck,
            "cards": cards_for_deck(deck),
            "tag_review_cards": deck_review_cards(deck),
            "query": "",
            "selected_tag": "",
            "selected_status": "",
            "selected_marked": "",
        },
    )


def card_list(request, deck_id):
    deck = get_deck(deck_id, request.user)
    query = request.GET.get("q", "")
    selected_tag = request.GET.get("tag", "")
    selected_status = request.GET.get("status", "")
    selected_marked = request.GET.get("marked", "")
    cards = filter_cards_for_deck(
        deck,
        query=query,
        tag=selected_tag,
        status=selected_status,
        marked=selected_marked,
    )
    return render(
        request,
        "cards/partials/card_list_refresh.html" if request.GET.get("refresh_meta") == "1" else "cards/partials/card_list.html",
        {
            "deck": deck,
            "cards": cards,
            "query": query,
            "selected_tag": selected_tag,
            "selected_status": selected_status,
            "selected_marked": selected_marked,
            "tag_review_cards": deck_review_cards(deck) if request.GET.get("refresh_meta") == "1" else [],
            "is_filtered": bool(
                query.strip()
                or selected_tag.strip()
                or selected_status.strip()
                or selected_marked.strip()
            ),
        },
    )


def deck_create(request):
    if request.method == "POST":
        post_data = request.POST.copy()
        populate_uploaded_json_text(post_data, request.FILES, "authoring_json_file", "authoring_json_text")
        form = DeckCreateForm(post_data, request.FILES, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                deck = form.save()
                if form.authoring_result:
                    create_cards_from_parsed(deck, form.authoring_result.cards, request.user)
            if request.htmx:
                return htmx_redirect(reverse("cards:home"))
            return redirect("cards:deck_detail", deck_id=deck.id)
    else:
        form = DeckCreateForm(user=request.user)

    template = "cards/partials/deck_form.html" if request.htmx else "cards/deck_form_page.html"
    return render(
        request,
        template,
        {
            "form": form,
            "title": "New deck",
            "submit_label": "Create deck",
            "action_url": reverse("cards:deck_create"),
            "category_names": list(categories_queryset(request.user).values_list("name", flat=True)),
        },
        status=422 if request.method == "POST" else 200,
    )


def deck_edit(request, deck_id):
    deck = get_deck(deck_id, request.user)
    if request.method == "POST":
        form = DeckForm(request.POST, instance=deck, user=request.user)
        if form.is_valid():
            deck = form.save()
            if request.htmx:
                return render(request, "cards/partials/deck_header.html", {"deck": deck})
            return redirect("cards:deck_detail", deck_id=deck.id)
    else:
        form = DeckForm(instance=deck, user=request.user)

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
            "category_names": list(categories_queryset(request.user).values_list("name", flat=True)),
        },
        status=422 if request.method == "POST" else 200,
    )


@require_POST
def deck_delete(request, deck_id):
    deck = get_deck(deck_id, request.user)
    deck.delete()
    if request.htmx:
        return htmx_redirect(reverse("cards:home"))
    return redirect("cards:home")


@require_POST
def deck_archive(request, deck_id):
    deck = get_deck(deck_id, request.user)
    archive_deck(deck)
    if request.htmx:
        return htmx_redirect(reverse("cards:home"))
    return redirect("cards:home")


@require_POST
def deck_restore(request, deck_id):
    deck = get_deck(deck_id, request.user)
    restore_deck(deck)
    if request.htmx:
        return htmx_redirect(reverse("cards:archived_decks"))
    return redirect("cards:archived_decks")


@require_POST
def deck_toggle_pin(request, deck_id):
    deck = get_deck(deck_id, request.user)
    toggle_deck_pin(deck)
    if request.htmx:
        return htmx_redirect(reverse("cards:home"))
    return redirect("cards:home")


@require_POST
def deck_toggle_favorite(request, deck_id):
    deck = get_deck(deck_id, request.user)
    toggle_deck_favorite(deck)
    if request.htmx:
        return render(request, "cards/partials/deck_card.html", {"deck": deck})
    return redirect("cards:home")


def card_editor_context(deck, form, saved=False):
    return {"deck": deck, "form": form, "title": "Add card", "saved": saved,
            "action_url": reverse("cards:card_create", kwargs={"deck_id": deck.id})}


def card_editor_saved(request, card):
    response = render(request, "cards/partials/card_editor_saved.html", {"card": card})
    response["X-Card-Saved"] = "true"
    response["X-Card-Continue"] = "true" if request.POST.get("intent") == "save_add_another" else "false"
    return response


@require_POST
def card_draft_preview(request, deck_id):
    deck = get_deck(deck_id, request.user)
    form = CardDraftPreviewForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "cards/partials/card_editor_errors.html", {"form": form}, status=422)
    data = form.cleaned_data
    current = get_card_for_deck(deck, data["card_id"], request.user) if data["card_id"] else None
    draft = Card(deck=deck, front=data["front"], back=data["back"],
                 content_format=data["content_format"], image_face=data["image_face"])
    if current and not data["remove_image"]:
        draft.image, draft.image_mime = current.image, current.image_mime
    if data["image_upload"]:
        draft.image, draft.image_mime = data["image_upload"]
    return render(request, "cards/partials/card_preview_surface.html", {
        "card": draft, "draft_preview": True,
        "rendered_front": render_card_face(draft, Card.ImageFace.FRONT),
        "rendered_back": render_card_face(draft, Card.ImageFace.BACK),
    })


def card_create(request, deck_id):
    deck = get_deck(deck_id, request.user)
    if request.method == "POST":
        form = CardForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            card = form.save(commit=False)
            card.deck = deck
            card.save()
            if request.headers.get("X-Card-Editor"):
                return card_editor_saved(request, card)
            if request.POST.get("intent") == "save_add_another":
                form = CardForm(initial={"content_format": card.content_format, "tags_text": ", ".join(card.tags)}, user=request.user)
                return render(request, "cards/card_form_page.html", card_editor_context(deck, form, saved=True))
            if request.htmx:
                return render(
                    request,
                    "cards/partials/card_create_success.html",
                    {"deck": deck, "card": card},
                    status=201,
                )
            return redirect("cards:deck_detail", deck_id=deck.id)
    else:
        form = CardForm(user=request.user)

    if request.method == "POST" and request.headers.get("X-Card-Editor"):
        return render(request, "cards/partials/card_editor_errors.html", {"form": form}, status=422)
    template = "cards/partials/card_form.html" if request.htmx else "cards/card_form_page.html"
    return render(
        request,
        template,
        {
            "form": form,
            "deck": deck,
            "title": "Add card",
            "submit_label": "Save",
            "editor_modal": bool(request.htmx),
            "action_url": reverse("cards:card_create", kwargs={"deck_id": deck.id}),
        },
        status=422 if request.method == "POST" else 200,
    )


def card_edit(request, deck_id, card_id):
    deck = get_deck(deck_id, request.user)
    card = get_card_for_deck(deck, card_id, request.user)
    if request.method == "POST":
        form = CardForm(
            request.POST,
            request.FILES,
            instance=card,
            card_id=str(card.id),
            user=request.user,
        )
        if form.is_valid():
            card = form.save()
            if request.headers.get("X-Card-Editor"):
                return card_editor_saved(request, card)
            if request.htmx:
                return render(request, "cards/partials/card_row.html", {"deck": deck, "card": card})
            return redirect("cards:deck_detail", deck_id=deck.id)
    else:
        form = CardForm(instance=card, user=request.user)

    if request.method == "POST" and request.headers.get("X-Card-Editor"):
        return render(request, "cards/partials/card_editor_errors.html", {"form": form}, status=422)
    template = "cards/partials/card_form.html" if request.htmx else "cards/card_form_page.html"
    return render(
        request,
        template,
        {
            "form": form,
            "deck": deck,
            "card": card,
            "title": "Edit card",
            "submit_label": "Save",
            "editor_modal": bool(request.htmx),
            "action_url": reverse(
                "cards:card_edit", kwargs={"deck_id": deck.id, "card_id": card.id}
            ),
        },
        status=422 if request.method == "POST" else 200,
    )


@require_POST
def card_preview(request, deck_id):
    deck = get_deck(deck_id, request.user)
    content_format = request.POST.get("content_format", Card.ContentFormat.PLAINTEXT)
    face = request.POST.get("face", Card.ImageFace.FRONT)
    if face not in {Card.ImageFace.FRONT, Card.ImageFace.BACK}:
        face = Card.ImageFace.FRONT
    content = request.POST.get("content")
    if content is None:
        content = request.POST.get(face, "")
    card = None
    card_id = request.POST.get("card_id")
    if card_id:
        card = get_card_for_deck(deck, card_id, request.user)
    image_data_uri = ""
    image_alt = ""
    if card and card.image_face == face:
        image_data_uri = render_card_face(card, face).image_data_uri
        image_alt = f"{card.get_image_face_display()} image"
    rendered_face = RenderedFace(
        html=render_content(content, content_format),
        image_data_uri=image_data_uri,
        image_alt=image_alt,
        enable_math=content_format == Card.ContentFormat.MARKDOWN,
    )
    return render(
        request,
        "cards/partials/card_preview.html",
        {"rendered_face": rendered_face, "target_id": f"{face}-preview"},
    )


def card_display_preview(request, deck_id, card_id):
    deck = get_deck(deck_id, request.user)
    card = get_card_for_deck(deck, card_id, request.user)
    return render(
        request,
        "cards/partials/card_display_preview.html",
        {
            "deck": deck,
            "card": card,
            "rendered_front": render_card_face(card, Card.ImageFace.FRONT),
            "rendered_back": render_card_face(card, Card.ImageFace.BACK),
        },
    )


@require_POST
def card_delete(request, deck_id, card_id):
    deck = get_deck(deck_id, request.user)
    card = get_card_for_deck(deck, card_id, request.user)
    card.delete()
    if request.htmx:
        return HttpResponse("")
    return redirect("cards:deck_detail", deck_id=deck.id)


def review_start(request, deck_id):
    return review_start_mode(request, deck_id, REVIEW_ALL_MODE)


def review_start_mode(request, deck_id, mode):
    deck = get_deck(deck_id, request.user)
    session = start_review_session(request, deck, mode)
    if review_is_complete(session):
        mode_label = session["mode_label"]
        clear_review_session(request)
        return render(request, "cards/review.html", {"deck": deck, "empty_mode_label": mode_label})

    return render(
        request,
        "cards/review.html",
        review_context(session),
    )


@require_POST
def review_start_tag(request, deck_id):
    deck = get_deck(deck_id, request.user)
    tags = request.POST.getlist("tags")
    tag_mode = request.POST.get("tag_mode", "include")
    session = start_review_session(
        request,
        deck,
        "tag",
        {"tags": tags, "exclude_tags": tag_mode == "exclude"},
    )
    if review_is_complete(session):
        mode_label = session["mode_label"]
        clear_review_session(request)
        return render(request, "cards/review.html", {"deck": deck, "empty_mode_label": mode_label})
    return render(request, "cards/review.html", review_context(session))


@require_POST
def review_grade(request, action):
    try:
        session = apply_review_action(request, action)
    except ValueError:
        return htmx_redirect(reverse("cards:home"))

    return render_review_session_response(request, session)


def render_review_session_response(request, session):
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
def review_mark(request):
    session = get_review_session(request)
    if not session or review_is_complete(session):
        return htmx_redirect(reverse("cards:home"))
    card = current_review_card(session)
    mark_card(card)
    return render(request, "cards/partials/review_card.html", review_context(session, initial_revealed=True))


def review_edit(request):
    session = get_review_session(request)
    if not session or review_is_complete(session):
        return htmx_redirect(reverse("cards:home"))
    if request.GET.get("cancel"):
        return render(request, "cards/partials/review_card.html", review_context(session))
    deck = session_deck(session)
    card = current_review_card(session)

    if request.method == "POST":
        form = CardForm(
            request.POST,
            request.FILES,
            instance=card,
            user=request.user,
        )
        if form.is_valid():
            form.save()
            return render(request, "cards/partials/review_card.html", review_context(session))
    else:
        form = CardForm(instance=card, user=request.user)

    return render(
        request,
        "cards/partials/review_edit_form.html",
        {"deck": deck, "card": card, "form": form},
        status=422 if request.method == "POST" else 200,
    )


@require_POST
def review_delete(request):
    session = get_review_session(request)
    if not session or review_is_complete(session):
        return htmx_redirect(reverse("cards:home"))
    card = current_review_card(session)
    session = remove_card_from_active_review(request, card)
    card.delete()
    return render_review_session_response(request, session)


@require_POST
def review_undo(request):
    session = undo_last_review_action(request)
    if not session:
        return htmx_redirect(reverse("cards:home"))
    return render(request, "cards/partials/review_card.html", review_context(session))


def review_context(session, initial_revealed=False):
    deck = session_deck(session)
    card = current_review_card(session)
    progress_current, progress_total = review_progress(session)
    user_settings = get_settings(deck.owner)
    return {
        "deck": deck,
        "card": card,
        "rendered_front": render_card_face(card, Card.ImageFace.FRONT),
        "rendered_back": render_card_face(card, Card.ImageFace.BACK),
        "session": session,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "can_undo": bool(session.get("log")),
        "is_hidden_mode": session.get("mode") == REVIEW_HIDDEN_MODE,
        "initial_revealed": initial_revealed,
        "show_tags_default": deck.show_tags_in_review,
        "review_swipe_enabled": user_settings.review_swipe_enabled,
    }


def bulk_import(request):
    raw_result = None
    json_result = None
    created_count = None
    post_data = request.POST.copy() if request.method == "POST" else None
    populate_uploaded_json_text(post_data, request.FILES, "authoring_json_file", "authoring_json_text")
    initial = {}
    if request.method == "GET" and request.GET.get("deck"):
        initial["deck"] = request.GET.get("deck")
    form = BulkImportForm(post_data or None, request.FILES or None, initial=initial, user=request.user)

    if request.method == "POST" and form.is_valid():
        intent = request.POST.get("intent", "raw_preview")
        if intent == "preview":
            intent = "raw_preview"
        elif intent == "confirm":
            intent = "raw_confirm"
        if intent.startswith("json_"):
            json_result = handle_authoring_json_import(request, form, intent)
            if isinstance(json_result, HttpResponse):
                return json_result
        else:
            raw_result = handle_raw_text_import(request, form, intent)
            if isinstance(raw_result, HttpResponse):
                return raw_result

    return render(
        request,
        "cards/bulk_import.html",
        {
            "form": form,
            "raw_result": raw_result,
            "json_result": json_result,
            "created_count": created_count,
        },
    )


def marked_cards(request):
    grouped = []
    current_deck = None
    current_cards = []
    for card in marked_cards_queryset(request.user):
        if current_deck is None or card.deck_id != current_deck.id:
            if current_deck is not None:
                grouped.append({"deck": current_deck, "cards": current_cards})
            current_deck = card.deck
            current_cards = []
        current_cards.append(card)
    if current_deck is not None:
        grouped.append({"deck": current_deck, "cards": current_cards})
    return render(
        request,
        "cards/marked_cards.html",
        {
            "groups": grouped,
            "decks": decks_queryset(request.user),
        },
    )


@require_POST
def marked_bulk_action(request):
    selected_ids = request.POST.getlist("cards")
    selected_cards = list(
        Card.objects.filter(
            id__in=selected_ids,
            is_marked=True,
            deck__owner=request.user,
        ).select_related("deck")
    )
    if not selected_cards:
        return redirect("cards:marked_cards")

    action = request.POST.get("bulk_action")
    if action == "tag":
        add_tags_to_cards(selected_cards, request.POST.get("tags_text", ""))
    elif action == "unmark":
        for card in selected_cards:
            unmark_card(card)
    elif action == "deck":
        target_deck = None
        new_deck_name = (request.POST.get("new_deck_name") or "").strip()
        if new_deck_name:
            target_deck = Deck.objects.create(name=new_deck_name, owner=request.user)
        else:
            deck_id = request.POST.get("deck")
            if deck_id:
                target_deck = get_deck(deck_id, request.user)
        if target_deck is not None:
            copy_cards_to_deck(selected_cards, target_deck)
            return redirect("cards:deck_detail", deck_id=target_deck.id)
    return redirect("cards:marked_cards")


@require_POST
def card_mark(request, deck_id, card_id):
    deck = get_deck(deck_id, request.user)
    card = get_card_for_deck(deck, card_id, request.user)
    mark_card(card)
    if request.htmx:
        return render(request, "cards/partials/card_row.html", {"deck": deck, "card": card})
    return redirect("cards:deck_detail", deck_id=deck.id)


@require_POST
def card_unmark(request, deck_id, card_id):
    deck = get_deck(deck_id, request.user)
    card = get_card_for_deck(deck, card_id, request.user)
    unmark_card(card)
    if request.htmx:
        if request.headers.get("HX-Target", "").startswith("card-"):
            return render(request, "cards/partials/card_row.html", {"deck": deck, "card": card})
        return HttpResponse("")
    return redirect("cards:marked_cards")


def import_target_deck(form, user, fallback_name=""):
    deck = form.cleaned_data.get("deck")
    if deck is not None:
        return deck
    new_deck_name = (form.cleaned_data.get("new_deck_name") or "").strip()
    if new_deck_name:
        return Deck.objects.create(name=new_deck_name, owner=user)
    if fallback_name:
        return Deck.objects.create(name=fallback_name, owner=user)
    return None


def handle_raw_text_import(request, form, intent):
    if not form.cleaned_data.get("deck") and not (form.cleaned_data.get("new_deck_name") or "").strip():
        form.add_error(None, "Choose a deck or enter a new deck name for raw text import.")
        return None
    text = form.cleaned_data.get("text", "")
    if not text.strip():
        form.add_error("text", "Paste raw card text before previewing.")
        return None
    result = parse_bulk_cards(text)
    if intent == "raw_confirm":
        deck = import_target_deck(form, request.user)
        create_cards_from_parsed(deck, result.cards, request.user)
        return redirect("cards:deck_detail", deck_id=deck.id)
    return result


def handle_authoring_json_import(request, form, intent):
    payload = form.cleaned_data.get("authoring_json_text", "")
    if not payload.strip():
        form.add_error("authoring_json_text", "Upload a JSON file or paste authoring JSON before previewing.")
        return None
    try:
        result = parse_authoring_json_cards(payload, request.user)
    except ValueError as exc:
        form.add_error("authoring_json_text", str(exc))
        return None
    if not form.cleaned_data.get("deck") and not (form.cleaned_data.get("new_deck_name") or "").strip() and not result.deck_name:
        form.add_error(None, "Choose a deck, enter a new deck name, or include a deck name in the JSON.")
        return result
    if intent == "json_confirm":
        deck = import_target_deck(form, request.user, fallback_name=result.deck_name)
        create_cards_from_parsed(deck, result.cards, request.user)
        return redirect("cards:deck_detail", deck_id=deck.id)
    return result


def settings_view(request):
    settings = get_settings(request.user)
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
            post_data = request.POST.copy()
            populate_uploaded_json_text(post_data, request.FILES, "backup_json_file", "backup_json_text")
            import_form = JsonImportForm(post_data, request.FILES)
            if import_form.is_valid():
                try:
                    import_result = import_backup(import_form.cleaned_data["backup_json_text"], request.user)
                except Exception as exc:
                    import_form.add_error("backup_json_text", f"Backup JSON could not be imported: {exc}")

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
    payload = export_backup(request.user)
    return json_response(payload, "flashcram-backup.json")


def export_deck(request, deck_id):
    deck = get_deck(deck_id, request.user)
    payload = export_backup(request.user, [deck])
    return json_response(payload, f"flashcram-{deck.id}.json")


def json_response(payload, filename):
    response = HttpResponse(
        json.dumps(payload, indent=2),
        content_type="application/json",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
