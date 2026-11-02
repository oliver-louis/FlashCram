from io import BytesIO
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from cards.models import Card
from cards.tests.utils import AuthenticatedTestCase, create_deck, test_user


EDITOR = {"HTTP_HX_REQUEST": "true", "HTTP_X_CARD_EDITOR": "true"}


def uploaded_image(color="blue"):
    buffer = BytesIO()
    Image.new("RGB", (40, 40), color).save(buffer, format="PNG")
    return SimpleUploadedFile("card.png", buffer.getvalue(), content_type="image/png")


class CardEditorTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.deck = create_deck()
        self.preview_url = reverse("cards:card_draft_preview", args=[self.deck.id])
        self.create_url = reverse("cards:card_create", args=[self.deck.id])
        self.payload = {"front": "Question", "back": "**Answer**", "content_format": "markdown", "image_face": "back", "status": "normal", "tags_text": "Biology, biology"}

    def preview(self, **overrides):
        return self.client.post(self.preview_url, self.payload | overrides, **EDITOR)

    def test_modal_and_standalone_share_editor(self):
        modal = self.client.get(self.create_url, **EDITOR)
        page = self.client.get(self.create_url)
        self.assertContains(modal, 'data-modal="true"')
        self.assertNotContains(modal, "<!doctype")
        self.assertContains(page, 'data-modal="false"')
        self.assertContains(page, "<!doctype")
        for response in (modal, page):
            self.assertContains(response, "Save and add another")
            self.assertContains(response, "Front formatting")
            self.assertContains(response, "More options")

    def test_preview_renders_both_faces_without_persistence(self):
        response = self.preview(front="\\(x_i\\)", back="Examples:\n\n- One\n- Two")
        self.assertContains(response, "arithmatex")
        self.assertContains(response, "<li>One</li>", html=True)
        self.assertContains(response, "toggleReveal()")
        self.assertEqual(Card.objects.count(), 0)
        self.assertNotIn("review_session", self.client.session)

    def test_preview_accepts_empty_faces(self):
        response = self.preview(front="", back="")
        self.assertContains(response, "Front is empty")
        self.assertContains(response, "Back is empty")
        self.assertEqual(Card.objects.count(), 0)

    def test_preview_plaintext_is_literal_and_escaped(self):
        response = self.preview(front="**literal** <script>alert(1)</script>", content_format="plaintext")
        self.assertContains(response, "**literal** &lt;script&gt;")
        self.assertNotContains(response, '<script>')
        self.assertNotContains(response, 'data-render-math="true"')

    def test_preview_uses_processed_upload_on_requested_face(self):
        response = self.preview(image_upload=uploaded_image(), image_face="front")
        self.assertTrue(response.context["rendered_front"].image_data_uri.startswith("data:image/png;base64,"))
        self.assertEqual(response.context["rendered_back"].image_data_uri, "")
        self.assertEqual(Card.objects.count(), 0)

    def test_preview_existing_image_move_remove_and_replace_are_disposable(self):
        image = uploaded_image().read()
        card = Card.objects.create(deck=self.deck, front="Saved", back="Saved", image=image, image_mime="image/png", image_face="back", times_reviewed=4, times_correct=2)
        original = (card.front, card.back, bytes(card.image), card.image_face, card.updated_at, card.times_reviewed, card.times_correct)
        response = self.preview(card_id=str(card.id), image_face="front")
        self.assertTrue(response.context["rendered_front"].image_data_uri)
        removed = self.preview(card_id=str(card.id), remove_image="on")
        self.assertEqual(removed.context["rendered_back"].image_data_uri, "")
        replacement = self.preview(card_id=str(card.id), remove_image="on", image_upload=uploaded_image("red"))
        self.assertTrue(replacement.context["rendered_back"].image_data_uri)
        self.assertNotEqual(bytes(replacement.context["card"].image), image)
        card.refresh_from_db()
        self.assertEqual((card.front, card.back, bytes(card.image), card.image_face, card.updated_at, card.times_reviewed, card.times_correct), original)
        self.assertEqual(Card.objects.count(), 1)

    def test_preview_invalid_image_returns_errors_only(self):
        response = self.preview(image_upload=SimpleUploadedFile("bad.png", b"not an image"))
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, 'data-error-field="image_upload"', status_code=422)
        self.assertNotContains(response, '<form', status_code=422)
        self.assertEqual(Card.objects.count(), 0)

    def test_preview_rejects_invalid_choices(self):
        for data in ({"content_format": "html"}, {"image_face": "both"}):
            with self.subTest(data=data):
                self.assertEqual(self.preview(**data).status_code, 422)

    def test_preview_owner_scope_and_card_deck_scope(self):
        other = create_deck(owner=test_user("other"))
        foreign_card = Card.objects.create(deck=other, front="Private", back="Private")
        self.assertEqual(self.client.post(reverse("cards:card_draft_preview", args=[other.id]), self.payload).status_code, 404)
        self.assertEqual(self.preview(card_id=str(foreign_card.id)).status_code, 404)
        second = create_deck(name="Second")
        same_owner_card = Card.objects.create(deck=second, front="Other deck", back="Back")
        self.assertEqual(self.preview(card_id=str(same_owner_card.id)).status_code, 404)
        self.assertEqual(self.preview(card_id=str(uuid4())).status_code, 404)

    def test_preview_malformed_card_id_is_a_validation_error(self):
        self.assertEqual(self.preview(card_id="not-a-uuid").status_code, 422)

    def test_preview_requires_login_and_post(self):
        self.assertEqual(self.client.get(self.preview_url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.preview().status_code, 302)

    def test_save_signals_success_and_normalizes_tags(self):
        response = self.client.post(self.create_url, self.payload, **EDITOR)
        self.assertEqual(response["X-Card-Saved"], "true")
        self.assertEqual(response["X-Card-Continue"], "false")
        self.assertContains(response, 'data-saved-tags="biology"')
        card = Card.objects.get()
        self.assertEqual(card.tags, ["biology"])
        self.assertEqual(card.deck.owner, self.user)

    def test_save_another_signals_continue_and_saves_once(self):
        response = self.client.post(self.create_url, self.payload | {"intent": "save_add_another"}, **EDITOR)
        self.assertEqual(response["X-Card-Continue"], "true")
        self.assertEqual(Card.objects.count(), 1)

    def test_invalid_save_returns_errors_without_replacing_inputs(self):
        response = self.client.post(self.create_url, self.payload | {"back": "", "status": "invalid", "image_upload": uploaded_image()}, **EDITOR)
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, 'data-error-field="back"', status_code=422)
        self.assertContains(response, 'data-error-field="status"', status_code=422)
        self.assertNotContains(response, '<form', status_code=422)
        self.assertNotContains(response, '<input', status_code=422)
        self.assertEqual(Card.objects.count(), 0)

    def test_edit_preserves_counters_and_updates_status_and_image(self):
        card = Card.objects.create(deck=self.deck, front="Old", back="Old", times_reviewed=5, times_correct=3, is_marked=True)
        response = self.client.post(reverse("cards:card_edit", args=[self.deck.id, card.id]), self.payload | {"status": "less", "image_upload": uploaded_image()}, **EDITOR)
        self.assertEqual(response["X-Card-Saved"], "true")
        card.refresh_from_db()
        self.assertEqual((card.times_reviewed, card.times_correct, card.is_marked, card.status), (5, 3, True, "less"))
        self.assertTrue(card.image)

    def test_standalone_save_and_continue_retains_only_format_and_tags(self):
        response = self.client.post(self.create_url, self.payload | {"intent": "save_add_another", "status": "hidden", "image_upload": uploaded_image()})
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertFalse(form.is_bound)
        self.assertEqual(form["content_format"].value(), "markdown")
        self.assertEqual(form["tags_text"].value(), "biology")
        self.assertEqual(form["status"].value(), "normal")
        self.assertFalse(form["front"].value())
        self.assertFalse(form["image_upload"].value())

    def test_list_refresh_keeps_filters_and_updates_counts_and_tags(self):
        Card.objects.create(deck=self.deck, front="Match", back="Back", tags=["newtag"])
        Card.objects.create(deck=self.deck, front="Excluded", back="Back")
        response = self.client.get(reverse("cards:card_list", args=[self.deck.id]), {"q": "Match", "tag": "newtag", "refresh_meta": "1"}, **EDITOR)
        self.assertContains(response, "Match")
        self.assertNotContains(response, "Excluded")
        self.assertContains(response, 'id="deck-card-count"')
        self.assertContains(response, 'value="newtag" selected')
        self.assertEqual(response.context["deck"].card_count, 2)

    def test_preview_return_control_is_in_header_and_close_is_icon(self):
        response = self.client.get(self.create_url, **EDITOR)
        html = response.content.decode()
        header = html.split('<header class="fc-editor-header">')[1].split('</header>')[0]
        self.assertIn('aria-label="Close editor"', header)
        self.assertIn('<svg', header)
        self.assertIn('x-ref="backToEditing"', header)
        self.assertEqual(html.count('x-ref="backToEditing"'), 1)
        self.assertIn(':data-keyboard-open="keyboardOpen"', html)

    def test_deck_header_reuses_pin_and_favourite_icons(self):
        self.deck.is_pinned = True
        self.deck.is_favorite = True
        self.deck.save()
        response = self.client.get(reverse('cards:deck_detail', args=[self.deck.id]))
        self.assertContains(response, 'aria-label="Pinned deck"')
        self.assertContains(response, 'aria-label="Favourite deck"')
        self.assertNotContains(response, '>Pinned</span>')
        self.assertNotContains(response, '>Favourite</span>')
