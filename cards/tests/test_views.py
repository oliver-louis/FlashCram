import json
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from pathlib import Path

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

    def test_home_deck_cards_are_mobile_compact_and_include_review_action(self):
        deck = Deck.objects.create(name="A very long deck title that should wrap on mobile instead of causing horizontal scrolling")
        Card.objects.create(deck=deck, front="front", back="back")

        response = self.client.get(reverse("cards:home"))

        self.assertContains(response, "line-clamp-2 break-words")
        self.assertContains(response, f'href="{reverse("cards:review_start", kwargs={"deck_id": deck.id})}"')
        self.assertContains(response, ">Review</a>")
        self.assertContains(response, "sm:hidden")
        self.assertContains(response, "hidden grid-cols-3")

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

    def test_deck_edit_form_keeps_htmx_target_after_outer_swap(self):
        deck = Deck.objects.create(name="Old", description="Before")

        form_response = self.client.get(
            reverse("cards:deck_edit", kwargs={"deck_id": deck.id}),
            **HTMX,
        )

        self.assertContains(form_response, 'id="deck-header"')
        self.assertContains(form_response, 'hx-target="#deck-header"')

        save_response = self.client.post(
            reverse("cards:deck_edit", kwargs={"deck_id": deck.id}),
            {"name": "Renamed", "description": "After"},
            **HTMX,
        )

        deck.refresh_from_db()
        self.assertEqual(deck.name, "Renamed")
        self.assertEqual(deck.description, "After")
        self.assertContains(save_response, 'id="deck-header"')
        self.assertContains(save_response, "Renamed")
        self.assertContains(save_response, "After")

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

    def test_card_create_form_suggests_existing_deck_tags(self):
        Card.objects.create(deck=self.deck, front="Existing", back="Back", tags=["linux", "shell"])

        response = self.client.get(reverse("cards:card_create", kwargs={"deck_id": self.deck.id}))

        self.assertContains(response, "Suggested tags from this deck")
        self.assertContains(response, 'data-tag="linux"')
        self.assertContains(response, 'data-tag="shell"')
        self.assertContains(response, "Use commas or spaces for multiple tags.")

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

    def test_card_row_mark_button_marks_card(self):
        card = Card.objects.create(deck=self.deck, front="Needs review", back="Back")

        response = self.client.post(
            reverse("cards:card_mark", kwargs={"deck_id": self.deck.id, "card_id": card.id}),
            **HTMX,
        )

        card.refresh_from_db()
        self.assertTrue(card.is_marked)
        self.assertContains(response, "Marked")
        self.assertContains(response, "Unmark")

    def test_card_row_preview_button_opens_review_style_fragment(self):
        card = Card.objects.create(
            deck=self.deck,
            front="Normal **bold**",
            back="Back text",
            content_format=Card.ContentFormat.MARKDOWN,
        )

        detail = self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": self.deck.id}))
        self.assertContains(detail, "card-preview-slot")
        self.assertContains(detail, "Preview")
        self.assertContains(
            detail,
            reverse("cards:card_display_preview", kwargs={"deck_id": self.deck.id, "card_id": card.id}),
        )

        response = self.client.get(
            reverse("cards:card_display_preview", kwargs={"deck_id": self.deck.id, "card_id": card.id}),
            **HTMX,
        )

        self.assertContains(response, 'id="card-preview-modal"')
        self.assertContains(response, "Card preview")
        self.assertContains(response, "Tap to reveal")
        self.assertContains(response, "<strong>bold</strong>", html=True)
        self.assertNotContains(response, "<!doctype html>")

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

    def test_normal_review_uses_primary_correct_incorrect_and_action_menu(self):
        self.make_card("first")

        response = self.start_review()

        self.assertNotContains(response, "text-2xl font-black leading-tight")
        self.assertContains(response, "text-2xl leading-tight")
        self.assertContains(response, "Incorrect")
        self.assertContains(response, "Correct")
        self.assertContains(response, "More review actions")
        self.assertContains(response, "grid-cols-[1fr_1fr_auto]")
        self.assertContains(response, "btn-square")
        self.assertContains(response, "Show Less")
        self.assertContains(response, "Mark")
        self.assertContains(response, "Edit")
        self.assertNotContains(response, ">Wrong</button>")
        self.assertNotContains(response, ">Got it</button>")

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

    def test_skip_advances_without_counter_changes_and_can_undo(self):
        first = self.make_card("first")
        second = self.make_card("second")
        start = self.start_review()
        self.assertContains(start, "Tap to flip back")
        self.assertContains(start, "Skip")

        response = self.grade("skip")

        first.refresh_from_db()
        session = self.client.session[REVIEW_SESSION_KEY]
        self.assertEqual(first.times_reviewed, 0)
        self.assertEqual(first.times_correct, 0)
        self.assertEqual(first.times_wrong, 0)
        self.assertEqual(session["cursor"], 1)
        self.assertEqual(
            session["summary"],
            {"reviewed": 0, "correct": 0, "wrong": 0, "marked_less": 0, "marked_hidden": 0},
        )
        self.assertContains(response, "second")

        undo = self.client.post(reverse("cards:review_undo"), **HTMX)
        session = self.client.session[REVIEW_SESSION_KEY]
        self.assertEqual(session["cursor"], 0)
        self.assertContains(undo, "first")

    def test_mark_marks_current_card_without_advancing_or_counter_changes(self):
        card = self.make_card("first")
        self.start_review()

        response = self.client.post(reverse("cards:review_mark"), **HTMX)

        card.refresh_from_db()
        session = self.client.session[REVIEW_SESSION_KEY]
        self.assertTrue(card.is_marked)
        self.assertEqual(card.times_reviewed, 0)
        self.assertEqual(session["cursor"], 0)
        self.assertContains(response, "revealed: true")
        self.assertContains(response, "Marked")
        self.assertContains(response, "first")

    def test_review_edit_updates_card_and_returns_to_session(self):
        card = self.make_card("old", tags=["before"])
        self.start_review()

        edit = self.client.get(reverse("cards:review_edit"), **HTMX)
        self.assertContains(edit, "Edit current card")
        self.assertContains(edit, "Delete")

        response = self.client.post(
            reverse("cards:review_edit"),
            {
                "front": "new front",
                "back": "new back",
                "tags_text": "after",
                "content_format": Card.ContentFormat.PLAINTEXT,
                "status": Card.Status.NORMAL,
                "image_face": Card.ImageFace.BACK,
            },
            **HTMX,
        )

        card.refresh_from_db()
        session = self.client.session[REVIEW_SESSION_KEY]
        self.assertEqual(card.front, "new front")
        self.assertEqual(card.back, "new back")
        self.assertEqual(card.tags, ["after"])
        self.assertEqual(session["cursor"], 0)
        self.assertContains(response, "new front")

    def test_review_delete_removes_current_and_future_queue_occurrences(self):
        first = self.make_card("first")
        second = self.make_card("second")
        self.start_review()
        session = self.client.session
        review = session[REVIEW_SESSION_KEY]
        review["queue"] = [str(first.id), str(second.id), str(first.id)]
        review["cursor"] = 0
        session[REVIEW_SESSION_KEY] = review
        session.save()

        response = self.client.post(reverse("cards:review_delete"), **HTMX)

        self.assertFalse(Card.objects.filter(pk=first.pk).exists())
        review = self.client.session[REVIEW_SESSION_KEY]
        self.assertEqual(review["queue"], [str(second.id)])
        self.assertEqual(review["cursor"], 0)
        self.assertContains(response, "second")

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
        self.assertNotContains(response, "Incorrect")
        self.assertNotContains(response, "Correct")

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

    def test_marked_page_lists_and_unmarks_marked_cards(self):
        marked = self.make_card("marked", is_marked=True)
        self.make_card("plain", is_marked=False)

        response = self.client.get(reverse("cards:marked_cards"))

        self.assertContains(response, "Marked cards")
        self.assertContains(response, "Bulk actions")
        self.assertContains(response, f'value="{marked.id}"')
        self.assertContains(response, "marked")
        self.assertNotContains(response, "plain")

        unmark = self.client.post(
            reverse("cards:card_unmark", kwargs={"deck_id": self.deck.id, "card_id": marked.id}),
            **{"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": f"marked-card-{marked.id}"},
        )

        marked.refresh_from_db()
        self.assertEqual(unmark.status_code, 200)
        self.assertEqual(unmark.content, b"")
        self.assertFalse(marked.is_marked)

    def test_marked_bulk_action_adds_tags_to_selected_cards(self):
        first = self.make_card("first", is_marked=True, tags=["old"])
        second = self.make_card("second", is_marked=True)
        unselected = self.make_card("third", is_marked=True)

        response = self.client.post(
            reverse("cards:marked_bulk_action"),
            {
                "cards": [str(first.id), str(second.id)],
                "bulk_action": "tag",
                "tags_text": "Important, old",
            },
        )

        first.refresh_from_db()
        second.refresh_from_db()
        unselected.refresh_from_db()
        self.assertRedirects(response, reverse("cards:marked_cards"))
        self.assertEqual(first.tags, ["old", "important"])
        self.assertEqual(second.tags, ["important", "old"])
        self.assertEqual(unselected.tags, [])

    def test_marked_bulk_action_copies_selected_cards_to_existing_or_new_deck(self):
        marked = self.make_card("marked", is_marked=True, tags=["review"])
        target = Deck.objects.create(name="Target")

        response = self.client.post(
            reverse("cards:marked_bulk_action"),
            {
                "cards": [str(marked.id)],
                "bulk_action": "deck",
                "deck": str(target.id),
            },
        )

        self.assertRedirects(response, reverse("cards:deck_detail", kwargs={"deck_id": target.id}))
        copied = Card.objects.get(deck=target)
        self.assertNotEqual(copied.id, marked.id)
        self.assertEqual(copied.front, marked.front)
        self.assertTrue(copied.is_marked)

        response = self.client.post(
            reverse("cards:marked_bulk_action"),
            {
                "cards": [str(marked.id)],
                "bulk_action": "deck",
                "new_deck_name": "New marked deck",
            },
        )

        new_deck = Deck.objects.get(name="New marked deck")
        self.assertRedirects(response, reverse("cards:deck_detail", kwargs={"deck_id": new_deck.id}))
        self.assertEqual(Card.objects.filter(deck=new_deck, front=marked.front).count(), 1)


class PhaseTwoViewTests(TestCase):
    def test_deck_detail_renders_phase_two_actions(self):
        deck = Deck.objects.create(name="Actions")
        Card.objects.create(deck=deck, front="front", back="back", tags=["shell"])

        response = self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": deck.id}))

        self.assertContains(response, "Random")
        self.assertContains(response, "Review weak")
        self.assertContains(response, "Bulk import")
        self.assertContains(response, "Review by tag")

    def test_deck_detail_places_review_before_deck_info(self):
        deck = Deck.objects.create(name="Order")

        response = self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": deck.id}))
        html = response.content.decode()

        self.assertLess(html.index(">Review<"), html.index(">Deck<"))

    def test_deck_detail_collapses_large_tag_lists_and_review_tags(self):
        deck = Deck.objects.create(name="Many tags")
        tags = [f"tag{i}" for i in range(1, 10)]
        Card.objects.create(deck=deck, front="front", back="back", tags=tags)

        response = self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": deck.id}))

        self.assertContains(response, "Show all 9 tags", count=2)
        self.assertContains(response, 'x-show="expanded"')
        self.assertContains(response, "tag8")
        self.assertContains(response, "tag9")

    def test_deck_detail_short_tag_lists_do_not_render_collapse_controls(self):
        deck = Deck.objects.create(name="Short tags")
        Card.objects.create(deck=deck, front="front", back="back", tags=[f"tag{i}" for i in range(1, 9)])

        response = self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": deck.id}))

        self.assertNotContains(response, "Show all 8 tags")
        self.assertNotContains(response, 'x-show="expanded"')

    def test_deck_detail_includes_mobile_overflow_guards(self):
        deck = Deck.objects.create(name="Overflow")
        Card.objects.create(
            deck=deck,
            front="A very long card front that should wrap instead of stretching the viewport",
            back="back",
            tags=["a-very-long-tag-name-that-should-not-force-horizontal-scroll"],
        )

        response = self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": deck.id}))

        self.assertContains(response, "flex min-w-0 max-w-full flex-col gap-6")
        self.assertNotContains(response, "fc-shell mx-auto flex w-full max-w-5xl flex-col overflow-x-hidden")
        self.assertNotContains(response, "flex max-w-full flex-col gap-6 overflow-x-hidden")
        self.assertContains(response, 'id="deck-header" class="fc-card max-w-full rounded-3xl')
        self.assertContains(response, "absolute bottom-full right-0")
        self.assertContains(response, "min-w-0 max-w-full overflow-hidden rounded-3xl")
        self.assertContains(response, "line-clamp-2 break-words")
        self.assertContains(response, "max-w-full truncate")

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

    def test_bulk_import_page_renders_separate_raw_and_json_panels(self):
        response = self.client.get(reverse("cards:bulk_import"))

        self.assertContains(response, "Raw text")
        self.assertContains(response, "Authoring JSON")
        self.assertContains(response, "Accepted raw-text formats")
        self.assertContains(response, "Accepted authoring JSON format")
        self.assertContains(response, "flashcram.cards.v1")
        self.assertContains(response, "Backup JSON files should be imported from Settings")

    def test_bulk_import_prefills_deck_from_query_parameter(self):
        deck = Deck.objects.create(name="Prefill target")

        detail = self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": deck.id}))
        self.assertContains(detail, f'?deck={deck.id}')

        response = self.client.get(reverse("cards:bulk_import"), {"deck": str(deck.id)})

        self.assertContains(response, "Prefill target")
        self.assertContains(response, f'<option value="{deck.id}" selected>Prefill target</option>')

    def test_authoring_json_file_preview_and_confirm_existing_deck(self):
        deck = Deck.objects.create(name="JSON target")
        payload = json.dumps(
            {
                "schema": "flashcram.cards.v1",
                "deck": "Ignored file deck",
                "cards": [
                    {"front": "F1", "back": "B1", "tags": ["Tag"], "format": "plaintext"},
                    {"front": "F2", "back": "**B2**", "tags": "md, tag", "format": "markdown"},
                ],
            }
        )

        preview = self.client.post(
            reverse("cards:bulk_import"),
            {
                "deck": str(deck.id),
                "new_deck_name": "",
                "intent": "json_preview",
                "authoring_json_file": SimpleUploadedFile(
                    "cards.json",
                    payload.encode(),
                    content_type="application/json",
                ),
            },
        )
        self.assertContains(preview, "Authoring JSON preview")
        self.assertContains(preview, "2 cards detected")
        self.assertContains(preview, "File deck: Ignored file deck")
        self.assertEqual(Card.objects.count(), 0)

        confirm = self.client.post(
            reverse("cards:bulk_import"),
            {
                "deck": str(deck.id),
                "new_deck_name": "",
                "intent": "json_confirm",
                "authoring_json_file": SimpleUploadedFile(
                    "cards.json",
                    payload.encode(),
                    content_type="application/json",
                ),
            },
        )
        self.assertEqual(confirm.status_code, 302)
        self.assertEqual(Deck.objects.count(), 1)
        self.assertEqual(Card.objects.count(), 2)
        self.assertEqual(Card.objects.get(front="F1").tags, ["tag"])
        self.assertEqual(Card.objects.get(front="F2").content_format, Card.ContentFormat.MARKDOWN)

    def test_authoring_json_creates_deck_from_file_name_when_no_target(self):
        payload = json.dumps(
            {
                "schema": "flashcram.cards.v1",
                "deck": "File Deck",
                "cards": [{"front": "Front", "back": "Back"}],
            }
        )

        response = self.client.post(
            reverse("cards:bulk_import"),
            {
                "deck": "",
                "new_deck_name": "",
                "intent": "json_confirm",
                "authoring_json_text": payload,
            },
        )

        self.assertEqual(response.status_code, 302)
        deck = Deck.objects.get(name="File Deck")
        self.assertEqual(deck.card_count, 1)

    def test_authoring_json_reimport_adds_duplicate_cards(self):
        deck = Deck.objects.create(name="Duplicate target")
        payload = json.dumps(
            {
                "schema": "flashcram.cards.v1",
                "cards": [{"front": "Same", "back": "Same back"}],
            }
        )
        post = {
            "deck": str(deck.id),
            "new_deck_name": "",
            "intent": "json_confirm",
            "authoring_json_text": payload,
        }

        self.client.post(reverse("cards:bulk_import"), post)
        self.client.post(reverse("cards:bulk_import"), post)

        self.assertEqual(Card.objects.filter(deck=deck, front="Same").count(), 2)

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


class PhaseThreePolishTests(TestCase):
    def setUp(self):
        self.deck = Deck.objects.create(name="Search deck")
        self.front_match = Card.objects.create(
            deck=self.deck,
            front="Kernel modules",
            back="Loaded with modprobe",
            tags=["linux"],
        )
        self.back_match = Card.objects.create(
            deck=self.deck,
            front="grep inverse",
            back="Use grep -v to exclude matching lines",
            tags=["shell"],
        )
        self.tag_match = Card.objects.create(
            deck=self.deck,
            front="CIDR",
            back="Subnet notation",
            tags=["network"],
        )
        self.marked_match = Card.objects.create(
            deck=self.deck,
            front="Marked CIDR",
            back="Marked subnet",
            tags=["network"],
            is_marked=True,
        )

    def test_card_filter_matches_front_back_tag_and_combined(self):
        front_response = self.client.get(
            reverse("cards:card_list", kwargs={"deck_id": self.deck.id}),
            {"q": "kernel"},
            **HTMX,
        )
        self.assertContains(front_response, "Kernel modules")
        self.assertNotContains(front_response, "grep inverse")

        back_response = self.client.get(
            reverse("cards:card_list", kwargs={"deck_id": self.deck.id}),
            {"q": "exclude"},
            **HTMX,
        )
        self.assertContains(back_response, "grep inverse")
        self.assertNotContains(back_response, "CIDR")

        tag_response = self.client.get(
            reverse("cards:card_list", kwargs={"deck_id": self.deck.id}),
            {"tag": "network"},
            **HTMX,
        )
        self.assertContains(tag_response, "CIDR")
        self.assertNotContains(tag_response, "Kernel modules")

        combined_response = self.client.get(
            reverse("cards:card_list", kwargs={"deck_id": self.deck.id}),
            {"q": "grep", "tag": "shell"},
            **HTMX,
        )
        self.assertContains(combined_response, "grep inverse")
        self.assertNotContains(combined_response, "CIDR")

    def test_card_filter_can_show_marked_and_unmarked_cards(self):
        marked_response = self.client.get(
            reverse("cards:card_list", kwargs={"deck_id": self.deck.id}),
            {"marked": "marked"},
            **HTMX,
        )
        self.assertContains(marked_response, "Marked CIDR")
        self.assertNotContains(marked_response, "Kernel modules")

        unmarked_response = self.client.get(
            reverse("cards:card_list", kwargs={"deck_id": self.deck.id}),
            {"marked": "unmarked"},
            **HTMX,
        )
        self.assertContains(unmarked_response, "Kernel modules")
        self.assertNotContains(unmarked_response, "Marked CIDR")

    def test_card_filter_combines_query_tag_status_and_marked(self):
        Card.objects.create(
            deck=self.deck,
            front="Hidden marked network",
            back="target",
            tags=["network"],
            status=Card.Status.HIDDEN,
            is_marked=True,
        )

        response = self.client.get(
            reverse("cards:card_list", kwargs={"deck_id": self.deck.id}),
            {
                "q": "hidden",
                "tag": "network",
                "status": Card.Status.HIDDEN,
                "marked": "marked",
            },
            **HTMX,
        )

        self.assertContains(response, "Hidden marked network")
        self.assertNotContains(response, "Marked CIDR")

    def test_card_filter_can_show_hidden_cards_only(self):
        Card.objects.create(deck=self.deck, front="Archived", back="Hidden back", status=Card.Status.HIDDEN)

        response = self.client.get(
            reverse("cards:card_list", kwargs={"deck_id": self.deck.id}),
            {"status": Card.Status.HIDDEN},
            **HTMX,
        )

        self.assertContains(response, "Archived")
        self.assertContains(response, "Hidden")
        self.assertNotContains(response, "Kernel modules")

    def test_card_filter_returns_fragment_and_no_match_empty_state(self):
        response = self.client.get(
            reverse("cards:card_list", kwargs={"deck_id": self.deck.id}),
            {"q": "notfound", "marked": "marked"},
            **HTMX,
        )

        self.assertContains(response, 'id="card-list"')
        self.assertContains(response, "No matching cards")
        self.assertNotContains(response, "<!doctype html>")

    def test_empty_states_render(self):
        Deck.objects.all().delete()
        home = self.client.get(reverse("cards:home"))
        self.assertContains(home, "No decks yet")

        empty_deck = Deck.objects.create(name="Empty")
        detail = self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": empty_deck.id}))
        self.assertContains(detail, "No cards yet")

        nothing = self.client.get(
            reverse("cards:review_start_mode", kwargs={"deck_id": empty_deck.id, "mode": "weak"})
        )
        self.assertContains(nothing, "Nothing to review")
        self.assertNotIn(REVIEW_SESSION_KEY, self.client.session)

    def test_theme_toggle_persists_dark_and_light_and_renders(self):
        for theme in [Settings.Theme.LIGHT, Settings.Theme.DARK]:
            response = self.client.post(
                reverse("cards:settings"),
                {
                    "form": "settings",
                    "theme": theme,
                    "weak_min_wrong": 2,
                    "weak_min_ratio": 0.33,
                    "show_less_weight": 0.25,
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(Settings.objects.get().theme, theme)
            home = self.client.get(reverse("cards:home"))
            self.assertContains(home, f'data-theme="{theme}"')


class UiAssetTests(TestCase):
    def test_nav_uses_theme_aware_brand_and_mobile_menu(self):
        response = self.client.get(reverse("cards:home"))

        self.assertContains(response, "fc-brand-text")
        self.assertContains(response, 'aria-label="Open navigation menu"')
        self.assertNotContains(response, "btm-nav")

    def test_core_static_assets_are_available_for_local_runserver(self):
        for path in [
            "css/app.css",
            "vendor/htmx.min.js",
            "vendor/alpine.min.js",
            "vendor/katex/katex.min.css",
            "vendor/katex/katex.min.js",
            "vendor/katex/auto-render.min.js",
            "vendor/mathlive/mathlive.min.mjs",
            "vendor/pygments/dark.css",
            "vendor/pygments/light.css",
            "icons/favicon.png",
        ]:
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path), path)

    def test_compiled_css_contains_brand_and_contrast_tokens(self):
        css_path = finders.find("css/app.css")
        self.assertIsNotNone(css_path)
        css = Path(css_path).read_text()

        for token in ["#005aff", "#00c6ff", "--fc-text:#102033", "--fc-text:#f4f8ff", ".fc-brand-text{color:#fff}", "[data-theme=light] .fc-brand-text{color:#000}"]:
            with self.subTest(token=token):
                self.assertIn(token, css)

    def test_base_template_links_compiled_assets_and_brand_icon(self):
        response = self.client.get(reverse("cards:home"))

        self.assertContains(response, "css/app.css")
        self.assertContains(response, "vendor/htmx.min.js")
        self.assertContains(response, "vendor/alpine.min.js")
        self.assertContains(response, "icons/favicon")
