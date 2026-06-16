# Generated for FlashCram P0.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Deck",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["created_at", "name"],
            },
        ),
        migrations.CreateModel(
            name="Settings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                (
                    "theme",
                    models.CharField(
                        choices=[("dark", "Dark"), ("light", "Light")],
                        default="dark",
                        max_length=20,
                    ),
                ),
                ("weak_min_wrong", models.PositiveIntegerField(default=2)),
                ("weak_min_ratio", models.FloatField(default=0.33)),
                ("show_less_weight", models.FloatField(default=0.25)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "settings",
                "verbose_name_plural": "settings",
            },
        ),
        migrations.CreateModel(
            name="Card",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("front", models.TextField()),
                ("back", models.TextField()),
                (
                    "content_format",
                    models.CharField(
                        choices=[("plaintext", "Plain text"), ("markdown", "Markdown")],
                        default="plaintext",
                        max_length=20,
                    ),
                ),
                ("tags", models.JSONField(blank=True, default=list)),
                ("times_reviewed", models.PositiveIntegerField(default=0)),
                ("times_correct", models.PositiveIntegerField(default=0)),
                ("times_wrong", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[("normal", "Normal"), ("less", "Show less"), ("hidden", "Hidden")],
                        default="normal",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "deck",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cards",
                        to="cards.deck",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            times_reviewed__gte=models.F("times_correct") + models.F("times_wrong")
                        ),
                        name="card_reviewed_covers_grade_counts",
                    )
                ],
            },
        ),
    ]
