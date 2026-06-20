from django.test import TestCase

from cards.models import Card, Category, Deck, Settings
from cards.tests.utils import create_category, create_deck, test_user
from cards.services import get_settings, normalize_tags


class SettingsTests(TestCase):
    def test_settings_accessor_returns_one_row_per_user(self):
        user = test_user("settings-a")
        first = get_settings(user)
        second = get_settings(user)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Settings.objects.count(), 1)

    def test_settings_are_isolated_per_user(self):
        user_a = test_user("settings-a")
        user_b = test_user("settings-b")
        settings_a = get_settings(user_a)
        settings_b = get_settings(user_b)

        settings_a.weak_min_wrong = 7
        settings_a.save()

        settings_b.refresh_from_db()
        self.assertEqual(Settings.objects.count(), 2)
        self.assertEqual(settings_b.weak_min_wrong, 2)

    def test_review_swipe_enabled_defaults_true(self):
        user = test_user("settings-swipe")
        settings = get_settings(user)

        self.assertTrue(settings.review_swipe_enabled)


class TagNormalizationTests(TestCase):
    def test_normalize_tags_from_iterable(self):
        self.assertEqual(
            normalize_tags([" Shell ", "shell", "", "PYTHON", " python ", "grep"]),
            ["shell", "python", "grep"],
        )

    def test_normalize_tags_from_string(self):
        self.assertEqual(
            normalize_tags(" Shell, shell  PYTHON,grep  "),
            ["shell", "python", "grep"],
        )

    def test_card_save_normalizes_tags(self):
        deck = create_deck(name="CLI")
        card = Card.objects.create(
            deck=deck,
            front="What does ls do?",
            back="Lists files",
            tags=[" Shell ", "shell", "FILES"],
        )

        self.assertEqual(card.tags, ["shell", "files"])

    def test_new_card_defaults_to_unmarked(self):
        deck = create_deck(name="Marked")
        card = Card.objects.create(deck=deck, front="Front", back="Back")

        self.assertFalse(card.is_marked)


class CategoryDeckModelTests(TestCase):
    def test_deck_can_be_uncategorized_or_assigned_to_category(self):
        category = create_category(name="CSSE2310")
        uncategorized = create_deck(name="Loose")
        categorized = create_deck(name="Exam", category=category)

        self.assertIsNone(uncategorized.category)
        self.assertEqual(categorized.category, category)

    def test_deleting_category_uncategorizes_decks(self):
        category = create_category(name="Economics")
        deck = create_deck(name="Final", category=category)

        category.delete()

        deck.refresh_from_db()
        self.assertIsNone(deck.category)

    def test_pin_favorite_and_archive_default_false(self):
        deck = create_deck(name="Defaults")

        self.assertFalse(deck.is_pinned)
        self.assertFalse(deck.is_favorite)
        self.assertFalse(deck.is_archived)


class ClassificationTests(TestCase):
    def setUp(self):
        self.user = test_user("classification")
        self.deck = create_deck(name="Exam", owner=self.user)
        self.settings = get_settings(self.user)

    def make_card(self, **kwargs):
        values = {
            "deck": self.deck,
            "front": "Front",
            "back": "Back",
        }
        values.update(kwargs)
        return Card.objects.create(**values)

    def test_unseen_card_is_not_weak_and_avoids_divide_by_zero(self):
        card = self.make_card(times_reviewed=0, times_correct=0, times_wrong=0)

        self.assertTrue(card.is_unseen)
        self.assertFalse(card.is_weak(self.settings))

    def test_card_below_min_wrong_is_not_weak(self):
        card = self.make_card(times_reviewed=3, times_correct=2, times_wrong=1)

        self.assertFalse(card.is_weak(self.settings))

    def test_card_below_ratio_is_not_weak(self):
        card = self.make_card(times_reviewed=10, times_correct=8, times_wrong=2)

        self.assertFalse(card.is_weak(self.settings))

    def test_card_at_ratio_boundary_is_weak(self):
        card = self.make_card(times_reviewed=6, times_correct=4, times_wrong=2)

        self.assertTrue(card.is_weak(self.settings))

    def test_card_above_thresholds_is_weak(self):
        card = self.make_card(times_reviewed=5, times_correct=2, times_wrong=3)

        self.assertTrue(card.is_weak(self.settings))

    def test_hidden_classification(self):
        card = self.make_card(status=Card.Status.HIDDEN)

        self.assertTrue(card.is_hidden)


class DeckDerivedHelperTests(TestCase):
    def test_deck_counts_and_tags(self):
        deck = create_deck(name="Mixed deck")
        Card.objects.create(deck=deck, front="new", back="new", tags=["shell", "CLI"])
        Card.objects.create(
            deck=deck,
            front="weak",
            back="weak",
            times_reviewed=5,
            times_correct=2,
            times_wrong=3,
            tags=["python"],
        )
        Card.objects.create(
            deck=deck,
            front="hidden",
            back="hidden",
            status=Card.Status.HIDDEN,
            times_reviewed=1,
            tags=["shell", "secret"],
        )
        Card.objects.create(
            deck=deck,
            front="less",
            back="less",
            status=Card.Status.LESS,
            times_reviewed=1,
            tags=[],
        )

        self.assertEqual(deck.card_count, 4)
        self.assertEqual(deck.unseen_count, 1)
        self.assertEqual(deck.weak_count, 1)
        self.assertEqual(deck.hidden_count, 1)
        self.assertEqual(deck.tags_used, ["cli", "python", "secret", "shell"])
