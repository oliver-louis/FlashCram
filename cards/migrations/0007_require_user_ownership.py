# Generated for FlashCram P6 staged multi-user migration.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Lower


def require_assigned_owners(apps, schema_editor):
    Category = apps.get_model("cards", "Category")
    Deck = apps.get_model("cards", "Deck")
    Settings = apps.get_model("cards", "Settings")
    if Category.objects.filter(owner__isnull=True).exists():
        raise RuntimeError(
            "Owner-less categories remain. Run `python manage.py assign_orphan_decks <username>` "
            "before applying this migration."
        )
    if Deck.objects.filter(owner__isnull=True).exists():
        raise RuntimeError(
            "Owner-less decks remain. Run `python manage.py assign_orphan_decks <username>` "
            "before applying this migration."
        )
    if Settings.objects.filter(user__isnull=True).exists():
        raise RuntimeError(
            "Legacy singleton settings remain. Run `python manage.py assign_orphan_decks <username>` "
            "before applying this migration."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0006_multi_user_nullable"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(require_assigned_owners, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="category",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="categories",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="deck",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="decks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="settings",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="flashcram_settings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                Lower("name"),
                "owner",
                name="unique_category_name_per_owner_ci",
            ),
        ),
    ]
