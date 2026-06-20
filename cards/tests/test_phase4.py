import base64
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from cards.models import Card, Deck, Settings
from cards.tests.utils import AuthenticatedTestCase, create_deck, test_user
from cards.rendering import card_image_data_uri, normalize_display_math_blocks, plain_text_preview, render_card_face, render_content
from cards.services import ImageProcessingError, export_backup, get_settings, import_backup, process_image_bytes


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

    def test_markdown_display_math_renders_without_manual_blank_lines(self):
        source = (
            "A person’s share of total payoff:\n"
            "\\[\n"
            "\\sigma_i=\\frac{x_i}{\\sum_j x_j}\n"
            "\\]\n"
            "\n"
            "Example: someone may dislike taking much more than their fair share of a cake."
        )

        rendered = str(render_content(source, Card.ContentFormat.MARKDOWN))

        self.assertIn("arithmatex", rendered)
        self.assertIn("\\[", rendered)
        self.assertIn("\\sigma_i=\\frac{x_i}{\\sum_j x_j}", rendered)
        self.assertIn("</div>", rendered)
        self.assertIn("<p>Example:", rendered)

    def test_display_math_spacing_normalization_skips_fenced_code(self):
        source = "Text:\n\\[\nx\n\\]\n\n```text\n\\[\nnot math\n\\]\n```"
        normalized = normalize_display_math_blocks(source)

        self.assertIn("Text:\n\n\\[\nx\n\\]\n", normalized)
        self.assertIn("```text\n\\[\nnot math\n\\]\n```", normalized)

    def test_markdown_does_not_enable_inline_dollar_math(self):
        rendered = str(render_content("$x$ $HOME $10.00", Card.ContentFormat.MARKDOWN))

        self.assertIn("$x$", rendered)
        self.assertIn("$HOME", rendered)
        self.assertIn("$10.00", rendered)
        self.assertNotIn("arithmatex", rendered)

    def test_markdown_math_delimiters_are_explicit_only(self):
        inline = str(render_content("\\(x_i\\)", Card.ContentFormat.MARKDOWN))
        display_square = str(render_content("\\[x_i\\]", Card.ContentFormat.MARKDOWN))
        display_dollar = str(render_content("$$x_i$$", Card.ContentFormat.MARKDOWN))
        protected_markdown = str(render_content("\\(*bold*\\)", Card.ContentFormat.MARKDOWN))
        old_helper_output = str(render_content("\\\\(*bold*\\\\)", Card.ContentFormat.MARKDOWN))

        self.assertIn("arithmatex", inline)
        self.assertIn("\\(x_i\\)", inline)
        self.assertIn("arithmatex", display_square)
        self.assertIn("\\[x_i\\]", display_square)
        self.assertIn("arithmatex", display_dollar)
        self.assertIn("\\[x_i\\]", display_dollar)
        self.assertIn("\\(*bold*\\)", protected_markdown)
        self.assertNotIn("<em>bold</em>", protected_markdown)
        self.assertNotIn("arithmatex", old_helper_output)

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
        self.assertIn("x", preview)
        self.assertNotIn("<span", preview)
        self.assertNotIn("\\(", preview)

    def test_plain_preview_unwraps_math_delimiters(self):
        preview = plain_text_preview(
            "Formula \\(x_i\\) and \\[y_2\\] and $$z_3$$",
            Card.ContentFormat.MARKDOWN,
        )

        self.assertIn("x_i", preview)
        self.assertIn("y_2", preview)
        self.assertIn("z_3", preview)
        for token in ["\\(", "\\[", "$$"]:
            self.assertNotIn(token, preview)

    def test_markdown_bullet_lists_render_with_visible_marker_styles(self):
        rendered = str(render_content("Possible explanations:\n\n- Altruism\n- Equality", Card.ContentFormat.MARKDOWN))
        css = Path("static_src/input.css").read_text()

        self.assertIn("<ul>", rendered)
        self.assertIn("<li>Altruism</li>", rendered)
        self.assertIn("list-style-type: disc", css)
        self.assertIn("list-style-type: decimal", css)
        self.assertIn("padding-inline-start", css)

    def test_rendered_math_has_mobile_overflow_guards(self):
        css = Path("static_src/input.css").read_text()

        self.assertIn(".fc-rendered-content :where(.arithmatex, .katex-display)", css)
        self.assertIn("querySelector('.katex-html')", Path("templates/base.html").read_text())
        self.assertIn(".fc-math-display-frame", css)
        self.assertIn(".fc-math-inline-frame", css)
        self.assertIn("--fc-math-scale", css)
        self.assertIn(":has(.fc-math-fit-subject)", css)
        self.assertIn("overflow-x: auto", css)
        self.assertIn("-webkit-overflow-scrolling: touch", css)

    def test_review_text_has_conservative_fit_guards(self):
        css = Path("static_src/input.css").read_text()
        html = Path("templates/base.html").read_text()

        self.assertIn("--fc-review-text-scale", css)
        self.assertIn("--fc-review-reserved-height", css)
        self.assertIn(".fc-review-face-fit > .fc-review-face-inner", css)
        self.assertIn("transform: scale(var(--fc-review-text-scale, 1))", css)
        self.assertIn("const minScale = 0.8", html)
        self.assertIn("window.flashcramFitReviewText = function(root)", html)
        self.assertIn("querySelectorAll('#review-panel .fc-review-content')", html)

    def test_review_swipe_surface_does_not_transform_layout_card(self):
        css = Path("static_src/input.css").read_text()
        review_template = Path("cards/templates/cards/partials/review_card.html").read_text()

        card_rule = css.split(".fc-review-card {", 1)[1].split("\n  }", 1)[0]
        self.assertNotIn("translate3d", card_rule)
        self.assertIn(".fc-review-card-stage", css)
        self.assertIn("contain: layout paint", css)
        self.assertIn("isolation: isolate", css)
        self.assertIn(".fc-review-card-surface", css)
        self.assertIn("transform: translate3d(var(--fc-swipe-x, 0), var(--fc-swipe-y, 0), 0) rotate(var(--fc-swipe-rotate, 0deg))", css)
        self.assertIn("will-change: transform", css)
        self.assertIn(".fc-review-card-returning", css)
        self.assertIn(".fc-review-card-committing", css)
        self.assertIn(".fc-shell:has(#review-panel)", css)
        self.assertIn("height: calc(100dvh - 5.5rem)", css)
        self.assertIn("overscroll-behavior: contain", css)
        self.assertIn("touch-action: pan-y", css)
        self.assertIn("user-select: none", css)
        self.assertIn("scrollHeight > content.clientHeight + 24", review_template)
        self.assertIn("this.swipe.axis = 'horizontal'", review_template)
        self.assertIn("this.swipe.axis = 'down'", review_template)
        self.assertIn("absX > 12 && absX > absY * 1.08", review_template)
        self.assertIn("Math.min(92, Math.max(54, width * 0.18))", review_template)
        self.assertIn("const downThreshold = 80", review_template)
        self.assertNotIn(".fc-rendered-content", review_template.split("interactiveSwipeTarget(target)", 1)[1].split("freshSwipeState()", 1)[0])
        self.assertNotIn("pre,", review_template.split("interactiveSwipeTarget(target)", 1)[1].split("freshSwipeState()", 1)[0])
        self.assertNotIn(".katex", review_template.split("interactiveSwipeTarget(target)", 1)[1].split("freshSwipeState()", 1)[0])


class PreviewViewTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.deck = create_deck(name="Preview deck")

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
        self.assertContains(response, 'data-render-math="true"')

    def test_preview_accepts_front_back_field_names_and_scopes_math(self):
        markdown = self.client.post(
            reverse("cards:card_preview", kwargs={"deck_id": self.deck.id}),
            {
                "front": "\\(x_i\\)",
                "content_format": Card.ContentFormat.MARKDOWN,
                "face": Card.ImageFace.FRONT,
            },
            **HTMX,
        )
        plaintext = self.client.post(
            reverse("cards:card_preview", kwargs={"deck_id": self.deck.id}),
            {
                "back": "\\(x_i\\)",
                "content_format": Card.ContentFormat.PLAINTEXT,
                "face": Card.ImageFace.BACK,
            },
            **HTMX,
        )

        self.assertContains(markdown, 'data-render-math="true"')
        self.assertContains(markdown, "\\(x_i\\)")
        self.assertContains(plaintext, 'id="back-preview"')
        self.assertContains(plaintext, "\\(x_i\\)")
        self.assertNotContains(plaintext, 'data-render-math="true"')

    def test_card_form_uses_debounced_preview_and_correct_equation_delimiters(self):
        response = self.client.get(reverse("cards:card_create", kwargs={"deck_id": self.deck.id}))
        html = response.content.decode()

        self.assertIn("hx-trigger=\"input changed delay:500ms\"", html)
        self.assertIn("hx-target=\"#front-preview\"", html)
        self.assertIn("hx-target=\"#back-preview\"", html)
        self.assertIn("? '\\\\[' + latex + '\\\\]'", html)
        self.assertIn(": '\\\\(' + latex + '\\\\)'", html)
        self.assertNotIn("'\\\\\\\\[' + latex", html)
        self.assertNotIn("'\\\\\\\\(' + latex", html)
        self.assertNotIn(">Preview</button>", html)

    def test_base_template_scopes_katex_to_markdown_fragments(self):
        response = self.client.get(reverse("cards:home"))
        html = response.content.decode()

        self.assertIn("window.flashcramFitMath = function(root)", html)
        self.assertIn("window.flashcramFitReviewText = function(root)", html)
        self.assertIn("querySelectorAll('[data-render-math=\"true\"]')", html)
        self.assertIn("querySelectorAll('#review-panel .fc-review-content')", html)
        self.assertIn("window.flashcramFitMath(scope)", html)
        self.assertIn("window.flashcramFitReviewText(scope)", html)
        self.assertIn("window.flashcramRenderMath(document)", html)
        self.assertIn('document.addEventListener("htmx:afterSwap"', html)
        self.assertIn('window.addEventListener("resize", window.flashcramRefitMath)', html)
        self.assertIn('window.addEventListener("orientationchange", window.flashcramRefitMath)', html)
        self.assertNotIn("flashcramRenderMath(document.body)", html)
        self.assertNotIn("renderMathInElement(root || document.body", html)

    def test_base_template_uses_theme_variables_for_page_shell(self):
        response = self.client.get(reverse("cards:home"))
        html = response.content.decode()

        self.assertIn("background: var(--fc-page, #111116)", html)
        self.assertNotIn("html, body { margin: 0; min-height: 100%; background: #111116", html)


class ImageCardTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.deck = create_deck(name="Images")

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

    def test_decompression_bomb_is_reported_as_image_processing_error(self):
        with patch("cards.services.Image.open", side_effect=Image.DecompressionBombError("boom")):
            with self.assertRaises(ImageProcessingError):
                process_image_bytes(b"not-empty")


class PhaseFourImportExportTests(AuthenticatedTestCase):
    def test_bulk_import_uses_default_content_format(self):
        settings = get_settings(self.user)
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
        deck = create_deck(name="Backup")
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

        payload = export_backup(self.user, [deck])
        exported_card = payload["decks"][0]["cards"][0]
        self.assertEqual(exported_card["image"], base64.b64encode(image).decode("ascii"))
        self.assertEqual(exported_card["imageMime"], "image/png")
        self.assertEqual(exported_card["imageFace"], "back")

        Deck.objects.all().delete()
        import_backup(payload, self.user)
        restored = Card.objects.get(id=card.id)
        self.assertEqual(restored.content_format, Card.ContentFormat.MARKDOWN)
        self.assertEqual(bytes(restored.image), image)
        self.assertEqual(restored.image_mime, "image/png")
        self.assertEqual(restored.image_face, Card.ImageFace.BACK)
