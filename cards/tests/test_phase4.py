import base64
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from cards.models import Card, Deck, Settings
from cards.rendering import card_image_data_uri, plain_text_preview, render_card_face, render_content
from cards.services import export_backup, import_backup


HTMX = {"HTTP_HX_REQUEST": "true"}


def image_bytes(size=(40, 40), color=(20, 90, 255), image_format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=image_format)
    return buffer.getvalue()


class RenderingTests(TestCase):
    def test_markdown_renders_code_and_katex_ready_math(self):
        source = "Inline \\(x_i^2\\)\n\n\\[y_2\\]\n\n$$z_3$$\n\n```python\nprint('hi')\n```"

        rendered = str(render_content(source, Card.ContentFormat.MARKDOWN))

        self.assertIn("arithmatex", rendered)
        self.assertIn("\\(x_i^2\\)", rendered)
        self.assertIn("\\[y_2\\]", rendered)
        self.assertIn("\\[z_3\\]", rendered)
        self.assertIn("highlight", rendered)
        self.assertIn("print", rendered)

    def test_plaintext_is_not_processed(self):
        rendered = str(render_content("$HOME *literal* _literal_\n<b>tag</b>", Card.ContentFormat.PLAINTEXT))

        self.assertIn("$HOME *literal* _literal_", rendered)
        self.assertIn("&lt;b&gt;tag&lt;/b&gt;", rendered)
        self.assertIn("<br>", rendered)
        self.assertNotIn("<em>", rendered)

    def test_plain_preview_strips_markdown(self):
        preview = plain_text_preview("**Bold** <span>raw</span> \\(x\\)", Card.ContentFormat.MARKDOWN)

        self.assertIn("Bold", preview)
        self.assertIn("raw", preview)
        self.assertNotIn("<span", preview)


class PreviewViewTests(TestCase):
    def setUp(self):
        self.deck = Deck.objects.create(name="Preview deck")

    def test_preview_returns_rendered_fragment(self):
        response = self.client.post(
            reverse("cards:card_preview", kwargs={"deck_id": self.deck.id}),
            {
                "content": "```python\nprint('hi')\n```\n\n\\(x_i\\)",
                "content_format": Card.ContentFormat.MARKDOWN,
                "face": Card.ImageFace.FRONT,
            },
            **HTMX,
        )

        self.assertContains(response, 'id="front-preview"')
        self.assertContains(response, "highlight")
        self.assertContains(response, "\\(x_i\\)")


class ImageCardTests(TestCase):
    def setUp(self):
        self.deck = Deck.objects.create(name="Images")

    def test_image_upload_rejects_disallowed_type(self):
        response = self.client.post(
            reverse("cards:card_create", kwargs={"deck_id": self.deck.id}),
            {
                "front": "front",
                "back": "back",
                "status": Card.Status.NORMAL,
                "image_face": Card.ImageFace.BACK,
                "image_upload": SimpleUploadedFile("bad.txt", b"not image", content_type="text/plain"),
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Unsupported image type", status_code=422)
        self.assertEqual(Card.objects.count(), 0)

    def test_image_upload_downscales_and_renders_on_correct_face(self):
        original = image_bytes(size=(1900, 1200), image_format="JPEG")
        response = self.client.post(
            reverse("cards:card_create", kwargs={"deck_id": self.deck.id}),
            {
                "front": "front",
                "back": "back",
                "status": Card.Status.NORMAL,
                "content_format": Card.ContentFormat.PLAINTEXT,
                "image_face": Card.ImageFace.FRONT,
                "image_upload": SimpleUploadedFile("card.jpg", original, content_type="image/jpeg"),
            },
            **HTMX,
        )

        self.assertEqual(response.status_code, 201)
        card = Card.objects.get()
        self.assertEqual(card.image_mime, "image/jpeg")
        self.assertEqual(card.image_face, Card.ImageFace.FRONT)
        self.assertLessEqual(len(card.image), 1_000_000)

        with Image.open(BytesIO(bytes(card.image))) as saved:
            self.assertLessEqual(max(saved.size), 1600)

        front = render_card_face(card, Card.ImageFace.FRONT)
        back = render_card_face(card, Card.ImageFace.BACK)
        self.assertTrue(front.image_data_uri.startswith("data:image/jpeg;base64,"))
        self.assertEqual(back.image_data_uri, "")

    def test_plaintext_card_with_image_and_no_image_render_cleanly(self):
        image = image_bytes()
        card = Card.objects.create(
            deck=self.deck,
            front="$HOME *literal*",
            back="back",
            image=image,
            image_mime="image/png",
            image_face=Card.ImageFace.BACK,
        )
        no_image = Card.objects.create(deck=self.deck, front="front", back="back")

        self.assertIn("$HOME *literal*", str(render_card_face(card, Card.ImageFace.FRONT).html))
        self.assertTrue(card_image_data_uri(card, Card.ImageFace.BACK).startswith("data:image/png;base64,"))
        self.assertEqual(render_card_face(no_image, Card.ImageFace.BACK).image_data_uri, "")


class PhaseFourImportExportTests(TestCase):
    def test_bulk_import_uses_default_content_format(self):
        settings = Settings.objects.get_or_create(pk=Settings.SINGLETON_PK)[0]
        settings.default_content_format = Settings.DefaultContentFormat.MARKDOWN
        settings.save()

        response = self.client.post(
            reverse("cards:bulk_import"),
            {
                "deck": "",
                "new_deck_name": "Markdown import",
                "text": "Front :: **Back**",
                "intent": "confirm",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Card.objects.get().content_format, Card.ContentFormat.MARKDOWN)

    def test_backup_round_trip_preserves_format_and_image(self):
        deck = Deck.objects.create(name="Backup")
        image = image_bytes()
        card = Card.objects.create(
            deck=deck,
            front="**Front**",
            back="\\[x^2\\]",
            content_format=Card.ContentFormat.MARKDOWN,
            tags=["math"],
            image=image,
            image_mime="image/png",
            image_face=Card.ImageFace.BACK,
        )

        payload = export_backup([deck])
        exported_card = payload["decks"][0]["cards"][0]
        self.assertEqual(exported_card["image"], base64.b64encode(image).decode("ascii"))
        self.assertEqual(exported_card["imageMime"], "image/png")
        self.assertEqual(exported_card["imageFace"], "back")

        Deck.objects.all().delete()
        import_backup(payload)
        restored = Card.objects.get(id=card.id)
        self.assertEqual(restored.content_format, Card.ContentFormat.MARKDOWN)
        self.assertEqual(bytes(restored.image), image)
        self.assertEqual(restored.image_mime, "image/png")
        self.assertEqual(restored.image_face, Card.ImageFace.BACK)
