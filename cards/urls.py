from django.urls import path

from . import views

app_name = "cards"

urlpatterns = [
    path("", views.home, name="home"),
    path("decks/new/", views.deck_create, name="deck_create"),
    path("decks/<uuid:deck_id>/", views.deck_detail, name="deck_detail"),
    path("decks/<uuid:deck_id>/edit/", views.deck_edit, name="deck_edit"),
    path("decks/<uuid:deck_id>/delete/", views.deck_delete, name="deck_delete"),
    path("decks/<uuid:deck_id>/cards/new/", views.card_create, name="card_create"),
    path(
        "decks/<uuid:deck_id>/cards/<uuid:card_id>/edit/",
        views.card_edit,
        name="card_edit",
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
    path("settings/", views.settings_view, name="settings"),
    path("export/", views.export_all, name="export_all"),
    path("review/grade/<str:action>/", views.review_grade, name="review_grade"),
    path("review/undo/", views.review_undo, name="review_undo"),
]
