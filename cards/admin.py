from django.contrib import admin

from .models import Card, Category, Deck, Settings


class CardInline(admin.TabularInline):
    model = Card
    extra = 0
    fields = (
        "front",
        "back",
        "content_format",
        "tags",
        "times_reviewed",
        "times_correct",
        "times_wrong",
        "status",
        "is_marked",
        "image_mime",
        "image_face",
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "deck_count", "created_at", "updated_at")
    list_filter = ("owner",)
    search_fields = ("name", "description", "owner__username", "owner__email")

    def deck_count(self, category):
        return category.decks.count()


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "category",
        "is_pinned",
        "is_favorite",
        "is_archived",
        "card_count",
        "created_at",
        "updated_at",
    )
    list_filter = ("owner", "category", "is_pinned", "is_favorite", "is_archived")
    search_fields = ("name", "description", "category__name", "owner__username", "owner__email")
    inlines = [CardInline]


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = (
        "front",
        "deck",
        "status",
        "is_marked",
        "times_reviewed",
        "times_correct",
        "times_wrong",
        "content_format",
        "image_face",
        "created_at",
    )
    list_filter = ("status", "is_marked", "content_format", "deck")
    search_fields = ("front", "back", "tags")


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "theme", "default_content_format", "weak_min_wrong", "weak_min_ratio", "show_less_weight")
    search_fields = ("user__username", "user__email")
