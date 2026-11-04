import uuid

from django.conf import settings as django_settings
from django.db import models
from django.db.models.functions import Lower

from .services import get_settings, is_weak_card, normalize_tags


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "created_at"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "owner",
                name="unique_category_name_per_owner_ci",
            )
        ]

    def __str__(self):
        return self.name


class Deck(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="decks",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        related_name="decks",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_favorite = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    show_tags_in_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "category__name", "created_at", "name"]

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
        user_settings = get_settings(self.owner)
        return sum(1 for card in self.cards.all() if is_weak_card(card, user_settings))

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

    class ImageFace(models.TextChoices):
        FRONT = "front", "Front"
        BACK = "back", "Back"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="cards")
    front = models.TextField()
    back = models.TextField()
    hint = models.TextField(blank=True, default="")
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
    image = models.BinaryField(null=True, blank=True)
    image_mime = models.CharField(max_length=40, blank=True, default="")
    image_face = models.CharField(
        max_length=10,
        choices=ImageFace.choices,
        default=ImageFace.BACK,
    )
    is_marked = models.BooleanField(default=False)
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
    class Theme(models.TextChoices):
        DARK = "dark", "Dark"
        LIGHT = "light", "Light"

    class DefaultContentFormat(models.TextChoices):
        PLAINTEXT = "plaintext", "Plain text"
        MARKDOWN = "markdown", "Markdown"

    user = models.OneToOneField(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="flashcram_settings",
    )
    theme = models.CharField(max_length=20, choices=Theme.choices, default=Theme.DARK)
    weak_min_wrong = models.PositiveIntegerField(default=2)
    weak_min_ratio = models.FloatField(default=0.33)
    show_less_weight = models.FloatField(default=0.25)
    default_content_format = models.CharField(
        max_length=20,
        choices=DefaultContentFormat.choices,
        default=DefaultContentFormat.PLAINTEXT,
    )
    review_swipe_enabled = models.BooleanField(default=True)
    generation_prompt_preferences = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "settings"
        verbose_name_plural = "settings"

    def __str__(self):
        return f"FlashCram settings for {self.user}"
