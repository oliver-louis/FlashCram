from django.urls import path

from . import views

app_name = "cards"

urlpatterns = [
    path("", views.home, name="home"),
    path("archived/", views.archived_decks, name="archived_decks"),
    path("decks/new/", views.deck_create, name="deck_create"),
    path("decks/<uuid:deck_id>/", views.deck_detail, name="deck_detail"),
    path("decks/<uuid:deck_id>/cards/", views.card_list, name="card_list"),
    path("decks/<uuid:deck_id>/edit/", views.deck_edit, name="deck_edit"),
    path("decks/<uuid:deck_id>/archive/", views.deck_archive, name="deck_archive"),
    path("decks/<uuid:deck_id>/restore/", views.deck_restore, name="deck_restore"),
    path("decks/<uuid:deck_id>/delete/", views.deck_delete, name="deck_delete"),
    path("decks/<uuid:deck_id>/pin/", views.deck_toggle_pin, name="deck_toggle_pin"),
    path("decks/<uuid:deck_id>/favorite/", views.deck_toggle_favorite, name="deck_toggle_favorite"),
    path("decks/<uuid:deck_id>/cards/new/", views.card_create, name="card_create"),
    path("decks/<uuid:deck_id>/cards/preview-draft/", views.card_draft_preview, name="card_draft_preview"),
    path("decks/<uuid:deck_id>/cards/preview/", views.card_preview, name="card_preview"),
    path(
        "decks/<uuid:deck_id>/cards/<uuid:card_id>/edit/",
        views.card_edit,
        name="card_edit",
    ),
    path(
        "decks/<uuid:deck_id>/cards/<uuid:card_id>/preview-display/",
        views.card_display_preview,
        name="card_display_preview",
    ),
    path(
        "decks/<uuid:deck_id>/cards/<uuid:card_id>/delete/",
        views.card_delete,
        name="card_delete",
    ),
    path("decks/<uuid:deck_id>/review/", views.review_start, name="review_start"),
    path(
        "decks/<uuid:deck_id>/review/tag/",
        views.review_start_tag,
        name="review_start_tag",
    ),
    path(
        "decks/<uuid:deck_id>/review/<str:mode>/",
        views.review_start_mode,
        name="review_start_mode",
    ),
    path("decks/<uuid:deck_id>/export/", views.export_deck, name="export_deck"),
    path("bulk-import/", views.bulk_import, name="bulk_import"),
    path("marked/", views.marked_cards, name="marked_cards"),
    path("marked/bulk/", views.marked_bulk_action, name="marked_bulk_action"),
    path("settings/", views.settings_view, name="settings"),
    path("export/", views.export_all, name="export_all"),
    path(
        "cards/<uuid:deck_id>/<uuid:card_id>/mark/",
        views.card_mark,
        name="card_mark",
    ),
    path(
        "cards/<uuid:deck_id>/<uuid:card_id>/unmark/",
        views.card_unmark,
        name="card_unmark",
    ),
    path("review/mark/", views.review_mark, name="review_mark"),
    path("review/edit/", views.review_edit, name="review_edit"),
    path("review/delete/", views.review_delete, name="review_delete"),
    path("review/grade/<str:action>/", views.review_grade, name="review_grade"),
    path("review/undo/", views.review_undo, name="review_undo"),
]
