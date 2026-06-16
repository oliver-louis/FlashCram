import json
import random

from django.test import TestCase

from cards.models import Card, Deck
from cards.services import (
    cards_for_review_mode,
    export_backup,
    import_backup,
    parse_bulk_cards,
    weighted_shuffle,
)


class ReviewModeServiceTests(TestCase):
    def setUp(self):
        self.deck = Deck.objects.create(name="Modes")

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


class JsonBackupTests(TestCase):
    def test_export_import_round_trip_and_reimport_does_not_duplicate(self):
        deck = Deck.objects.create(name="Backup", description="Round trip")
        card = Card.objects.create(
            deck=deck,
            front="Front",
            back="Back",
            tags=["shell"],
            times_reviewed=3,
            times_correct=2,
            times_wrong=1,
            status=Card.Status.LESS,
        )
        payload = export_backup()

        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["decks"][0]["id"], str(deck.id))
        self.assertEqual(payload["decks"][0]["cards"][0]["contentFormat"], "plaintext")

        Deck.objects.all().delete()
        result = import_backup(json.dumps(payload))
        self.assertEqual(result, {"decks": 1, "cards": 1})

        restored_deck = Deck.objects.get(id=deck.id)
        restored_card = Card.objects.get(id=card.id)
        self.assertEqual(restored_deck.name, "Backup")
        self.assertEqual(restored_card.tags, ["shell"])
        self.assertEqual(restored_card.times_wrong, 1)
        self.assertEqual(restored_card.status, Card.Status.LESS)

        import_backup(payload)
        self.assertEqual(Deck.objects.count(), 1)
        self.assertEqual(Card.objects.count(), 1)
