import json
import re
from django.test import SimpleTestCase
from cards.rendering import render_content, plain_text_preview
from cards.diagrams import diagram_error
from cards.services import parse_authoring_json_cards
from cards.tests.utils import AuthenticatedTestCase, create_deck
from django.urls import reverse

FENCE = '```mermaid\nflowchart TD\n A --> B\n```'

class DiagramRenderingTests(SimpleTestCase):
    def test_shared_render_and_summary(self):
        rendered = render_content('Text\n\n' + FENCE, 'markdown')
        self.assertIn('data-mermaid="pending"', rendered)
        self.assertIn('A --&gt; B', rendered)
        self.assertEqual(plain_text_preview(FENCE, 'markdown'), 'Diagram')
        self.assertNotIn('data-mermaid', render_content(FENCE, 'plaintext'))
        self.assertNotIn('data-mermaid', render_content('```python\nprint(1)\n```', 'markdown'))

    def test_type_allowlist_and_prohibited_content(self):
        for kind in ['flowchart TD', 'sequenceDiagram', 'stateDiagram-v2', 'classDiagram', 'erDiagram', 'mindmap', 'pie', 'xychart-beta']:
            self.assertEqual(diagram_error(kind + '\n A --> B'), '')
        for source in ['gantt\nfoo', 'flowchart TD\nclick A "javascript:alert(1)"', '%%{init: {}}%%\nflowchart TD', '---\nconfig: x\n---\nflowchart TD', 'flowchart TD\nA[<script>x</script>]', 'flowchart TD\nclassDef x fill:red', 'flowchart TD\nA@{img: "x"}']:
            self.assertTrue(diagram_error(source), source)
            rendered = render_content('```mermaid\n' + source + '\n```', 'markdown')
            self.assertIn('data-mermaid="error"', rendered)
            self.assertNotIn('<script>', rendered)

    def test_raw_html_cannot_forge_a_diagram_placeholder(self):
        source = '<div data-mermaid="pending" data-no-swipe="true"><pre><code>flowchart TD; click A "url"</code></pre></div>'
        self.assertNotIn('data-mermaid', render_content(source, 'markdown'))

    def test_limits_do_not_drop_source_or_other_content(self):
        rendered = render_content(('\n\n'.join([FENCE] * 5)) + '\n\nRest', 'markdown')
        self.assertEqual(rendered.count('data-mermaid="pending"'), 4)
        self.assertIn('at most four', rendered)
        self.assertIn('Rest', rendered)
        self.assertTrue(diagram_error('flowchart TD\n' + 'x' * 10000))

class DiagramImportTests(AuthenticatedTestCase):
    def test_authoring_preserves_source_and_preview_renders(self):
        payload = {'schema':'flashcram.cards.v1', 'cards':[{'front':'Question','back':FENCE,'format':'markdown','tags':[]}]}
        parsed = parse_authoring_json_cards(json.dumps(payload), self.user)
        self.assertEqual(parsed.cards[0].back, FENCE)
        deck = create_deck()
        response = self.client.post(reverse('cards:card_draft_preview', args=[deck.id]), {'front':'Question','back':FENCE,'content_format':'markdown','image_face':'back'})
        self.assertContains(response, 'data-mermaid="pending"')
        self.assertEqual(deck.cards.count(), 0)

    def test_documentation_examples_are_json_and_prompt_is_optional(self):
        response = self.client.get(reverse('cards:bulk_import'))
        self.assertContains(response, 'Do not add diagrams by default.')
        self.assertContains(response, 'Do not aim for a diagram quota')
        from pathlib import Path
        html = Path('cards/templates/cards/bulk_import.html').read_text()
        decoder = json.JSONDecoder()
        examples = re.findall(r'(?m)^\{\n', html)
        self.assertGreaterEqual(len(examples), 5)
        for match in re.finditer(r'(?m)^\{\n', html):
            decoder.raw_decode(html[match.start():])

    def test_bulk_new_deck_copy_and_backup_preserve_diagrams(self):
        from cards.models import Card, Deck
        from cards.services import copy_cards_to_deck, export_backup, import_backup
        payload = json.dumps({'schema':'flashcram.cards.v1', 'deck':'Diagram import', 'cards':[{'front':'Question','back':FENCE,'format':'markdown','tags':['diagram']}]})
        response = self.client.post(reverse('cards:bulk_import'), {'intent':'json_confirm', 'authoring_json_text':payload})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse('cards:deck_create'), {'name':'Diagram new deck', 'authoring_json_text':payload})
        self.assertEqual(response.status_code, 302)
        for card in Card.objects.all():
            self.assertEqual(card.back, FENCE)
        target = create_deck(name='Copy target')
        copy_cards_to_deck(Card.objects.filter(deck__name='Diagram import'), target)
        self.assertEqual(target.cards.get().back, FENCE)
        backup = export_backup(self.user)
        Card.objects.update(back='Changed')
        import_backup(backup, self.user)
        self.assertTrue(all(card.back == FENCE for card in Card.objects.all()))

    def test_mixed_content_and_inline_directives(self):
        source = FENCE + '\n\nInline \\(x_i\\)\n\n```python\nprint(1)\n```'
        rendered = render_content(source, 'markdown')
        self.assertIn('arithmatex', rendered)
        self.assertIn('highlight', rendered)
        self.assertIn('data-mermaid="pending"', rendered)
        self.assertTrue(diagram_error('flowchart TD; click A "url"'))
        self.assertTrue(diagram_error('flowchart TD\nA --> B\n%%{init: {}}%%'))
