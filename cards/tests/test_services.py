import json
import random

from django.test import TestCase

from cards.models import Card, Category, Deck, Settings
from cards.tests.utils import create_category, create_deck, test_user
from cards.services import (
    archive_deck,
    archived_decks_queryset,
    cards_for_review_mode,
    create_cards_from_parsed,
    deck_home_groups,
    decks_queryset,
    export_backup,
    import_backup,
    parse_authoring_json_cards,
    parse_bulk_cards,
    toggle_deck_favorite,
    toggle_deck_pin,
    restore_deck,
    weighted_shuffle,
    get_settings,
)


class ReviewModeServiceTests(TestCase):
    def setUp(self):
        self.deck = create_deck(name="Modes")

    def card(self, front, **kwargs):
        values = {"deck": self.deck, "front": front, "back": f"{front} back"}
        values.update(kwargs)
        return Card.objects.create(**values)

    def test_weighted_sampler_excludes_zero_weight_and_each_card_once(self):
        normal = self.card("normal")
        less = self.card("less", status=Card.Status.LESS)
        self.card("hidden", status=Card.Status.HIDDEN)

        result = weighted_shuffle(list(Card.objects.all()), rng=random.Random(1))

        self.assertCountEqual([card.id for card in result], [normal.id, less.id])
        self.assertEqual(len(result), len({card.id for card in result}))

    def test_weighted_sampler_is_seeded_and_less_skews_later(self):
        normal_positions = []
        less_positions = []
        for seed in range(200):
            Card.objects.all().delete()
            normal = self.card(f"normal-{seed}")
            less = self.card(f"less-{seed}", status=Card.Status.LESS)
            result = weighted_shuffle([normal, less], rng=random.Random(seed))
            normal_positions.append(result.index(normal))
            less_positions.append(result.index(less))

        seeded_once = [card.front for card in weighted_shuffle(list(Card.objects.all()), rng=random.Random(10))]
        seeded_twice = [card.front for card in weighted_shuffle(list(Card.objects.all()), rng=random.Random(10))]

        self.assertEqual(seeded_once, seeded_twice)
        self.assertGreater(sum(less_positions) / len(less_positions), sum(normal_positions) / len(normal_positions))

    def test_review_mode_queues(self):
        normal = self.card("normal", tags=["shell"])
        less = self.card("less", status=Card.Status.LESS, tags=["python"])
        weak = self.card(
            "weak",
            times_reviewed=5,
            times_correct=2,
            times_wrong=3,
            tags=["grep", "shell"],
        )
        unseen = self.card("unseen")
        hidden = self.card("hidden", status=Card.Status.HIDDEN, tags=["shell"])

        self.assertEqual(cards_for_review_mode(self.deck, "all"), [normal, less, weak, unseen])
        self.assertEqual(cards_for_review_mode(self.deck, "tag", {"tags": ["shell"]}), [normal, weak])
        self.assertEqual(
            cards_for_review_mode(self.deck, "tag", {"tags": ["shell"], "exclude_tags": True}),
            [less, unseen],
        )
        self.assertEqual(
            cards_for_review_mode(self.deck, "tag", {"tags": [], "exclude_tags": True}),
            [normal, less, weak, unseen],
        )
        self.assertEqual(cards_for_review_mode(self.deck, "weak"), [weak])
        self.assertEqual(cards_for_review_mode(self.deck, "unseen"), [normal, less, unseen])
        self.assertEqual(cards_for_review_mode(self.deck, "hidden"), [hidden])


class BulkParserTests(TestCase):
    def test_single_line_parser_trailing_tags_and_first_split(self):
        result = parse_bulk_cards(
            "Front :: Back with :: inside #Shell #grep\n"
            "Malformed line\n"
            "Other :: Answer #grep\n"
        )

        self.assertEqual(result.detected_format, "single-line")
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(len(result.cards), 2)
        self.assertEqual(result.cards[0].front, "Front")
        self.assertEqual(result.cards[0].back, "Back with :: inside")
        self.assertEqual(result.cards[0].tags, ["shell", "grep"])

    def test_multiline_parser_tags_and_skipped_count(self):
        result = parse_bulk_cards(
            "Q: What is grep?\n"
            "A: Search text\n"
            "Tags: Shell, grep\n\n"
            "Q: Missing answer\n\n"
            "A: Missing question\n"
        )

        self.assertEqual(result.detected_format, "multi-line")
        self.assertEqual(len(result.cards), 1)
        self.assertEqual(result.cards[0].tags, ["shell", "grep"])
        self.assertEqual(result.skipped_count, 2)

    def test_authoring_json_parser_accepts_llm_card_schema(self):
        result = parse_authoring_json_cards(
            json.dumps(
                {
                    "schema": "flashcram.cards.v1",
                    "deck": "Exam deck",
                    "cards": [
                        {
                            "front": "Question",
                            "back": "Answer",
                            "tags": [" Shell ", "shell", "Exam"],
                            "format": "plaintext",
                        },
                        {
                            "front": "Markdown?",
                            "back": "**Yes**",
                            "tags": "md, exam",
                            "contentFormat": "markdown",
                        },
                    ],
                }
            )
        )

        self.assertEqual(result.detected_format, "authoring-json")
        self.assertEqual(result.schema, "flashcram.cards.v1")
        self.assertEqual(result.deck_name, "Exam deck")
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(len(result.cards), 2)
        self.assertEqual(result.cards[0].tags, ["shell", "exam"])
        self.assertEqual(result.cards[1].tags, ["md", "exam"])
        self.assertEqual(result.cards[1].content_format, Card.ContentFormat.MARKDOWN)

    def test_authoring_json_parser_defaults_format_and_skips_malformed_cards(self):
        user = test_user("authoring-defaults")
        settings = get_settings(user)
        settings.default_content_format = Settings.DefaultContentFormat.MARKDOWN
        settings.save()

        result = parse_authoring_json_cards(
            {
                "schema": "flashcram.cards.v1",
                "cards": [
                    {"front": "Uses default", "back": "Back", "tags": None},
                    {"front": "", "back": "Missing front"},
                    {"front": "Bad format", "back": "Back", "format": "html"},
                    {"front": "Bad tags", "back": "Back", "tags": {"no": "thanks"}},
                ],
            },
            user,
        )

        self.assertEqual(len(result.cards), 1)
        self.assertEqual(result.skipped_count, 3)
        self.assertEqual(result.cards[0].content_format, Card.ContentFormat.MARKDOWN)

    def test_authoring_json_rejects_backup_json(self):
        with self.assertRaisesMessage(ValueError, "full backup JSON"):
            parse_authoring_json_cards({"version": 1, "decks": []})

    def test_create_cards_from_parsed_uses_authoring_content_format(self):
        deck = create_deck(name="Import deck")
        result = parse_authoring_json_cards(
            {
                "schema": "flashcram.cards.v1",
                "cards": [{"front": "Front", "back": "**Back**", "format": "markdown"}],
            }
        )

        create_cards_from_parsed(deck, result.cards)

        self.assertEqual(Card.objects.get().content_format, Card.ContentFormat.MARKDOWN)


class DeckOrganizationServiceTests(TestCase):
    def test_grouping_orders_pinned_then_categories_then_uncategorized_without_duplicates(self):
        science = create_category(name="Science")
        maths = create_category(name="Maths")
        pinned = create_deck(name="Pinned", category=science, is_pinned=True)
        maths_deck = create_deck(name="Algebra", category=maths)
        science_deck = create_deck(name="Physics", category=science)
        loose = create_deck(name="Loose")

        groups = deck_home_groups()

        self.assertEqual(groups["pinned"], [pinned])
        self.assertEqual([group["category"] for group in groups["category_groups"]], [maths, science])
        self.assertEqual(groups["category_groups"][0]["decks"], [maths_deck])
        self.assertEqual(groups["category_groups"][1]["decks"], [science_deck])
        self.assertEqual(groups["uncategorized"], [loose])
        self.assertNotIn(pinned, groups["category_groups"][1]["decks"])
        self.assertTrue(groups["has_categories"])
        self.assertTrue(groups["show_grouped_home"])

    def test_grouping_ignores_empty_category_records(self):
        create_category(name="Unused")
        loose = create_deck(name="Loose")

        groups = deck_home_groups()

        self.assertEqual(groups["pinned"], [])
        self.assertEqual(groups["category_groups"], [])
        self.assertEqual(groups["uncategorized"], [loose])
        self.assertFalse(groups["has_categories"])
        self.assertFalse(groups["show_grouped_home"])

    def test_grouping_with_pins_and_no_categories_keeps_unpinned_decks(self):
        pinned = create_deck(name="Pinned", is_pinned=True)
        loose = create_deck(name="Loose")

        groups = deck_home_groups()

        self.assertEqual(groups["pinned"], [pinned])
        self.assertEqual(groups["category_groups"], [])
        self.assertEqual(groups["uncategorized"], [loose])
        self.assertFalse(groups["has_categories"])
        self.assertTrue(groups["show_grouped_home"])

    def test_pin_and_favorite_toggles_are_independent(self):
        deck = create_deck(name="Flags")

        toggle_deck_pin(deck)
        deck.refresh_from_db()
        self.assertTrue(deck.is_pinned)
        self.assertFalse(deck.is_favorite)

        toggle_deck_favorite(deck)
        deck.refresh_from_db()
        self.assertTrue(deck.is_pinned)
        self.assertTrue(deck.is_favorite)

    def test_archive_and_restore_toggles_deck_visibility(self):
        deck = create_deck(name="Old")

        archive_deck(deck)
        deck.refresh_from_db()
        self.assertTrue(deck.is_archived)
        self.assertNotIn(deck, list(decks_queryset()))
        self.assertIn(deck, list(archived_decks_queryset()))

        restore_deck(deck)
        deck.refresh_from_db()
        self.assertFalse(deck.is_archived)
        self.assertIn(deck, list(decks_queryset()))
        self.assertNotIn(deck, list(archived_decks_queryset()))

    def test_home_grouping_excludes_archived_decks(self):
        category = create_category(name="Course")
        active = create_deck(name="Active", category=category)
        archived = create_deck(name="Archived", category=category, is_archived=True, is_pinned=True)

        groups = deck_home_groups()

        self.assertEqual(groups["pinned"], [])
        self.assertEqual(groups["category_groups"][0]["decks"], [active])
        self.assertNotIn(archived, groups["category_groups"][0]["decks"])

    def test_archived_decks_queryset_is_user_scoped(self):
        user_a = test_user("archive-a")
        user_b = test_user("archive-b")
        own = create_deck(name="Own archive", owner=user_a, is_archived=True)
        create_deck(name="Other archive", owner=user_b, is_archived=True)
        create_deck(name="Own active", owner=user_a)

        self.assertEqual(list(archived_decks_queryset(user_a)), [own])


class JsonBackupTests(TestCase):
    def test_export_import_round_trip_and_reimport_does_not_duplicate(self):
        user = test_user("backup-user")
        category = create_category(name="Course", owner=user, description="Term 1")
        deck = create_deck(
            name="Backup",
            owner=user,
            description="Round trip",
            category=category,
            is_favorite=True,
            is_pinned=True,
            is_archived=True,
        )
        card = Card.objects.create(
            deck=deck,
            front="Front",
            back="Back",
            tags=["shell"],
            times_reviewed=3,
            times_correct=2,
            times_wrong=1,
            status=Card.Status.LESS,
            is_marked=True,
        )
        payload = export_backup(user)

        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["categories"][0]["id"], str(category.id))
        self.assertEqual(payload["categories"][0]["name"], "Course")
        self.assertEqual(payload["decks"][0]["id"], str(deck.id))
        self.assertEqual(payload["decks"][0]["categoryId"], str(category.id))
        self.assertTrue(payload["decks"][0]["isFavorite"])
        self.assertTrue(payload["decks"][0]["isPinned"])
        self.assertTrue(payload["decks"][0]["isArchived"])
        self.assertEqual(payload["decks"][0]["cards"][0]["contentFormat"], "plaintext")
        self.assertTrue(payload["decks"][0]["cards"][0]["isMarked"])

        Deck.objects.all().delete()
        result = import_backup(json.dumps(payload), user)
        self.assertEqual(result, {"decks": 1, "cards": 1})

        restored_deck = Deck.objects.get(id=deck.id)
        restored_card = Card.objects.get(id=card.id)
        self.assertEqual(restored_deck.name, "Backup")
        self.assertEqual(restored_deck.category.name, "Course")
        self.assertTrue(restored_deck.is_favorite)
        self.assertTrue(restored_deck.is_pinned)
        self.assertTrue(restored_deck.is_archived)
        self.assertEqual(restored_card.tags, ["shell"])
        self.assertEqual(restored_card.times_wrong, 1)
        self.assertEqual(restored_card.status, Card.Status.LESS)
        self.assertTrue(restored_card.is_marked)

        import_backup(payload, user)
        self.assertEqual(Category.objects.count(), 1)
        self.assertEqual(Deck.objects.count(), 1)
        self.assertEqual(Card.objects.count(), 1)

    def test_import_older_backup_defaults_deck_organization_fields(self):
        user = test_user("old-backup-user")
        payload = {
            "version": 1,
            "decks": [
                {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "name": "Old",
                    "description": "",
                    "cards": [],
                }
            ],
        }

        import_backup(payload, user)

        deck = Deck.objects.get()
        self.assertEqual(deck.owner, user)
        self.assertIsNone(deck.category)
        self.assertFalse(deck.is_favorite)
        self.assertFalse(deck.is_pinned)
        self.assertFalse(deck.is_archived)
