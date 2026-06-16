from django.test import TestCase
from django.urls import reverse

from cards.models import Card, Deck, Settings
from cards.services import REVIEW_SESSION_KEY


HTMX = {"HTTP_HX_REQUEST": "true"}


class DeckCrudViewTests(TestCase):
    def test_home_lists_deck_counts(self):
        deck = Deck.objects.create(name="Linux")
        Card.objects.create(deck=deck, front="ls", back="list")
        Card.objects.create(deck=deck, front="secret", back="hidden", status=Card.Status.HIDDEN)

        response = self.client.get(reverse("cards:home"))

        self.assertContains(response, "Linux")
        self.assertContains(response, "2")
        self.assertContains(response, "hidden")

    def test_deck_create_htmx_returns_card_fragment(self):
        response = self.client.post(
            reverse("cards:deck_create"),
            {"name": "Networking", "description": "CIDR and ports"},
            **HTMX,
        )

        self.assertEqual(response.status_code, 201)
        self.assertContains(response, "Networking", status_code=201)
        self.assertEqual(Deck.objects.count(), 1)

    def test_deck_edit_htmx_returns_header_fragment(self):
        deck = Deck.objects.create(name="Old")

        response = self.client.post(
            reverse("cards:deck_edit", kwargs={"deck_id": deck.id}),
            {"name": "New", "description": "Updated"},
            **HTMX,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New")
        deck.refresh_from_db()
        self.assertEqual(deck.name, "New")

    def test_deck_delete_htmx_cascades_cards_and_redirects(self):
        deck = Deck.objects.create(name="Delete me")
        Card.objects.create(deck=deck, front="front", back="back")

        response = self.client.post(
            reverse("cards:deck_delete", kwargs={"deck_id": deck.id}),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["HX-Redirect"], reverse("cards:home"))
        self.assertEqual(Deck.objects.count(), 0)
        self.assertEqual(Card.objects.count(), 0)


class CardCrudViewTests(TestCase):
    def setUp(self):
        self.deck = Deck.objects.create(name="Deck")

    def test_card_create_htmx_returns_fragment_and_normalizes_tags(self):
        response = self.client.post(
            reverse("cards:card_create", kwargs={"deck_id": self.deck.id}),
            {
                "front": "What is grep?",
                "back": "A search tool",
                "tags_text": " Shell, shell grep ",
                "status": Card.Status.NORMAL,
            },
            **HTMX,
        )

        self.assertEqual(response.status_code, 201)
        self.assertContains(response, "What is grep?", status_code=201)
        card = Card.objects.get()
        self.assertEqual(card.tags, ["shell", "grep"])
        self.assertEqual(card.content_format, Card.ContentFormat.PLAINTEXT)

    def test_card_edit_htmx_returns_row_fragment(self):
        card = Card.objects.create(deck=self.deck, front="Old", back="Back")

        response = self.client.post(
            reverse("cards:card_edit", kwargs={"deck_id": self.deck.id, "card_id": card.id}),
            {
                "front": "New",
                "back": "Updated",
                "tags_text": "python",
                "status": Card.Status.LESS,
            },
            **HTMX,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New")
        card.refresh_from_db()
        self.assertEqual(card.front, "New")
        self.assertEqual(card.status, Card.Status.LESS)
        self.assertEqual(card.tags, ["python"])

    def test_card_delete_htmx_returns_empty_fragment(self):
        card = Card.objects.create(deck=self.deck, front="Gone", back="Back")

        response = self.client.post(
            reverse("cards:card_delete", kwargs={"deck_id": self.deck.id, "card_id": card.id}),
            **HTMX,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertFalse(Card.objects.filter(pk=card.pk).exists())


class ReviewAllViewTests(TestCase):
    def setUp(self):
        self.deck = Deck.objects.create(name="Review deck")

    def make_card(self, front, **kwargs):
        values = {"deck": self.deck, "front": front, "back": f"{front} back"}
        values.update(kwargs)
        return Card.objects.create(**values)

    def start_review(self):
        return self.client.get(reverse("cards:review_start", kwargs={"deck_id": self.deck.id}))

    def grade(self, action):
        return self.client.post(reverse("cards:review_grade", kwargs={"action": action}), **HTMX)

    def test_review_all_excludes_hidden_and_preserves_order(self):
        first = self.make_card("first")
        second = self.make_card("second", status=Card.Status.LESS)
        self.make_card("hidden", status=Card.Status.HIDDEN)

        response = self.start_review()
        session = self.client.session[REVIEW_SESSION_KEY]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(session["queue"], [str(first.id), str(second.id)])
        self.assertContains(response, "first")

    def test_each_grading_action_applies_expected_delta(self):
        expectations = {
            "got_it": {"times_reviewed": 1, "times_correct": 1, "times_wrong": 0, "status": Card.Status.NORMAL},
            "wrong": {"times_reviewed": 1, "times_correct": 0, "times_wrong": 1, "status": Card.Status.NORMAL},
            "show_less": {"times_reviewed": 1, "times_correct": 0, "times_wrong": 0, "status": Card.Status.LESS},
            "hide": {"times_reviewed": 1, "times_correct": 0, "times_wrong": 0, "status": Card.Status.HIDDEN},
        }

        for action, expected in expectations.items():
            with self.subTest(action=action):
                Card.objects.all().delete()
                card = self.make_card(action)
                self.start_review()

                self.grade(action)

                card.refresh_from_db()
                for field, value in expected.items():
                    self.assertEqual(getattr(card, field), value)

    def test_wrong_requeues_card_later_in_session(self):
        first = self.make_card("first")
        second = self.make_card("second")
        self.start_review()

        response = self.grade("wrong")
        session = self.client.session[REVIEW_SESSION_KEY]

        self.assertEqual(session["queue"], [str(first.id), str(second.id), str(first.id)])
        self.assertEqual(session["cursor"], 1)
        self.assertContains(response, "second")

        response = self.grade("got_it")
        self.assertContains(response, "first")

    def test_undo_reverses_deltas_status_cursor_summary_and_requeue(self):
        first = self.make_card("first")
        second = self.make_card("second")
        self.start_review()
        self.grade("wrong")

        response = self.client.post(reverse("cards:review_undo"), **HTMX)

        first.refresh_from_db()
        session = self.client.session[REVIEW_SESSION_KEY]
        self.assertEqual(first.times_reviewed, 0)
        self.assertEqual(first.times_wrong, 0)
        self.assertEqual(first.status, Card.Status.NORMAL)
        self.assertEqual(session["queue"], [str(first.id), str(second.id)])
        self.assertEqual(session["cursor"], 0)
        self.assertEqual(
            session["summary"],
            {"reviewed": 0, "correct": 0, "wrong": 0, "marked_less": 0, "marked_hidden": 0},
        )
        self.assertContains(response, "first")

    def test_session_advances_to_summary_and_clears(self):
        first = self.make_card("first")
        second = self.make_card("second")
        self.start_review()

        self.grade("got_it")
        response = self.grade("hide")

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.times_correct, 1)
        self.assertEqual(second.status, Card.Status.HIDDEN)
        self.assertContains(response, "Session complete")
        self.assertContains(response, "reviewed")
        self.assertNotIn(REVIEW_SESSION_KEY, self.client.session)

    def test_hidden_mode_restore_keep_hidden_and_undo(self):
        first = self.make_card("first", status=Card.Status.HIDDEN)
        second = self.make_card("second", status=Card.Status.HIDDEN)

        response = self.client.get(
            reverse("cards:review_start_mode", kwargs={"deck_id": self.deck.id, "mode": "hidden"})
        )
        session = self.client.session[REVIEW_SESSION_KEY]
        self.assertEqual(session["queue"], [str(first.id), str(second.id)])
        self.assertContains(response, "Hidden cards")
        self.assertContains(response, "Restore")

        response = self.grade("restore")
        first.refresh_from_db()
        self.assertEqual(first.status, Card.Status.NORMAL)
        self.assertContains(response, "second")

        response = self.client.post(reverse("cards:review_undo"), **HTMX)
        first.refresh_from_db()
        session = self.client.session[REVIEW_SESSION_KEY]
        self.assertEqual(first.status, Card.Status.HIDDEN)
        self.assertEqual(session["cursor"], 0)
        self.assertContains(response, "first")

        self.grade("keep_hidden")
        first.refresh_from_db()
        self.assertEqual(first.status, Card.Status.HIDDEN)


class PhaseTwoViewTests(TestCase):
    def test_deck_detail_renders_phase_two_actions(self):
        deck = Deck.objects.create(name="Actions")
        Card.objects.create(deck=deck, front="front", back="back", tags=["shell"])

        response = self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": deck.id}))

        self.assertContains(response, "Random")
        self.assertContains(response, "Review weak")
        self.assertContains(response, "Bulk import")
        self.assertContains(response, "Review by tag")

    def test_bulk_import_preview_and_confirm_existing_deck(self):
        deck = Deck.objects.create(name="Import target")
        payload = {
            "deck": str(deck.id),
            "new_deck_name": "",
            "text": "Q1 :: A1 #tag\nbad line\nQ2 :: A2",
        }

        preview = self.client.post(reverse("cards:bulk_import"), {**payload, "intent": "preview"})
        self.assertContains(preview, "2 cards detected")
        self.assertContains(preview, "1 lines skipped")
        self.assertEqual(Card.objects.count(), 0)

        confirm = self.client.post(reverse("cards:bulk_import"), {**payload, "intent": "confirm"})
        self.assertEqual(confirm.status_code, 302)
        self.assertEqual(Card.objects.count(), 2)
        self.assertEqual(Card.objects.first().tags, ["tag"])

    def test_bulk_import_can_create_new_deck(self):
        response = self.client.post(
            reverse("cards:bulk_import"),
            {
                "deck": "",
                "new_deck_name": "New import",
                "text": "Front :: Back",
                "intent": "confirm",
            },
        )

        self.assertEqual(response.status_code, 302)
        deck = Deck.objects.get(name="New import")
        self.assertEqual(deck.card_count, 1)

    def test_settings_persist_and_render_theme(self):
        response = self.client.post(
            reverse("cards:settings"),
            {
                "form": "settings",
                "theme": Settings.Theme.LIGHT,
                "weak_min_wrong": 3,
                "weak_min_ratio": 0.5,
                "show_less_weight": 0.1,
            },
        )
        self.assertEqual(response.status_code, 302)

        settings = Settings.objects.get()
        self.assertEqual(settings.theme, Settings.Theme.LIGHT)
        self.assertEqual(settings.weak_min_wrong, 3)
        self.assertEqual(settings.weak_min_ratio, 0.5)
        self.assertEqual(settings.show_less_weight, 0.1)

        home = self.client.get(reverse("cards:home"))
        self.assertContains(home, 'data-theme="light"')

    def test_json_export_and_import_view(self):
        deck = Deck.objects.create(name="Exportable")
        Card.objects.create(deck=deck, front="Front", back="Back")

        export = self.client.get(reverse("cards:export_all"))
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export["Content-Type"], "application/json")
        data = export.json()
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["decks"][0]["name"], "Exportable")

        Deck.objects.all().delete()
        response = self.client.post(
            reverse("cards:settings"),
            {"form": "json_import", "backup_json": export.content.decode()},
        )
        self.assertContains(response, "Imported 1 decks and 1 cards.")
        self.assertEqual(Deck.objects.count(), 1)
        self.assertEqual(Card.objects.count(), 1)
