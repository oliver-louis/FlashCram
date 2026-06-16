from django.contrib import admin

from .models import Card, Deck, Settings


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
    )


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("name", "card_count", "created_at", "updated_at")
    search_fields = ("name", "description")
    inlines = [CardInline]


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = (
        "front",
        "deck",
        "status",
        "times_reviewed",
        "times_correct",
        "times_wrong",
        "created_at",
    )
    list_filter = ("status", "content_format", "deck")
    search_fields = ("front", "back", "tags")


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ("theme", "weak_min_wrong", "weak_min_ratio", "show_less_weight")

    def has_add_permission(self, request):
        return not Settings.objects.exists()
