import uuid

from django.db import models

from .services import get_settings, is_weak_card, normalize_tags


class Deck(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "name"]

    def __str__(self):
        return self.name

    @property
    def card_count(self) -> int:
        return self.cards.count()

    @property
    def unseen_count(self) -> int:
        return self.cards.filter(times_reviewed=0).count()

    @property
    def weak_count(self) -> int:
        settings = get_settings()
        return sum(1 for card in self.cards.all() if is_weak_card(card, settings))

    @property
    def hidden_count(self) -> int:
        return self.cards.filter(status=Card.Status.HIDDEN).count()

    @property
    def tags_used(self) -> list[str]:
        tags = set()
        for card in self.cards.all():
            tags.update(card.tags or [])
        return sorted(tags)


class Card(models.Model):
    class ContentFormat(models.TextChoices):
        PLAINTEXT = "plaintext", "Plain text"
        MARKDOWN = "markdown", "Markdown"

    class Status(models.TextChoices):
        NORMAL = "normal", "Normal"
        LESS = "less", "Show less"
        HIDDEN = "hidden", "Hidden"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="cards")
    front = models.TextField()
    back = models.TextField()
    content_format = models.CharField(
        max_length=20,
        choices=ContentFormat.choices,
        default=ContentFormat.PLAINTEXT,
    )
    tags = models.JSONField(default=list, blank=True)
    times_reviewed = models.PositiveIntegerField(default=0)
    times_correct = models.PositiveIntegerField(default=0)
    times_wrong = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NORMAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    times_reviewed__gte=models.F("times_correct") + models.F("times_wrong")
                ),
                name="card_reviewed_covers_grade_counts",
            )
        ]

    def __str__(self):
        return self.front[:80]

    def save(self, *args, **kwargs):
        self.tags = normalize_tags(self.tags)
        super().save(*args, **kwargs)

    @property
    def is_unseen(self) -> bool:
        return self.times_reviewed == 0

    @property
    def is_hidden(self) -> bool:
        return self.status == self.Status.HIDDEN

    def is_weak(self, settings=None) -> bool:
        return is_weak_card(self, settings)


class Settings(models.Model):
    SINGLETON_PK = 1

    class Theme(models.TextChoices):
        DARK = "dark", "Dark"
        LIGHT = "light", "Light"

    id = models.PositiveSmallIntegerField(
        primary_key=True,
        default=SINGLETON_PK,
        editable=False,
    )
    theme = models.CharField(max_length=20, choices=Theme.choices, default=Theme.DARK)
    weak_min_wrong = models.PositiveIntegerField(default=2)
    weak_min_ratio = models.FloatField(default=0.33)
    show_less_weight = models.FloatField(default=0.25)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "settings"
        verbose_name_plural = "settings"

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    def __str__(self):
        return "FlashCram settings"
