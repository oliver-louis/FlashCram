from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from cards.models import Category, Deck, Settings


class Command(BaseCommand):
    help = "Assign owner-less decks/categories and legacy settings to a user before final P6 migrations."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User {username!r} does not exist.") from exc

        orphan_categories = Category.objects.filter(owner__isnull=True)
        category_count = orphan_categories.update(owner=user)

        orphan_decks = Deck.objects.filter(owner__isnull=True)
        deck_count = orphan_decks.update(owner=user)

        legacy_settings = Settings.objects.filter(user__isnull=True).first()
        user_settings = Settings.objects.filter(user=user).first()
        settings_action = "unchanged"
        if legacy_settings and user_settings and legacy_settings.pk != user_settings.pk:
            for field in (
                "theme",
                "weak_min_wrong",
                "weak_min_ratio",
                "show_less_weight",
                "default_content_format",
            ):
                setattr(user_settings, field, getattr(legacy_settings, field))
            user_settings.save()
            legacy_settings.delete()
            settings_action = "copied"
        elif legacy_settings:
            legacy_settings.user = user
            legacy_settings.save()
            settings_action = "assigned"
        elif not user_settings:
            Settings.objects.create(user=user)
            settings_action = "created"

        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned {deck_count} decks and {category_count} categories to {username}; "
                f"settings {settings_action}."
            )
        )
