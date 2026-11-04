import json
from django.urls import reverse
from cards.models import Card
from cards.forms import CardForm
from cards.rendering import render_card_face
from cards.services import parse_authoring_json_cards, copy_cards_to_deck, export_backup, import_backup
from cards.tests.utils import AuthenticatedTestCase, create_deck, test_user

EDITOR = {'HTTP_HX_REQUEST':'true', 'HTTP_X_CARD_EDITOR':'true'}

class HintTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.deck = create_deck()
        self.payload = {'front':'Question','back':'Answer','hint':'Think in layers.','content_format':'markdown','image_face':'back','status':'normal'}
        self.create = reverse('cards:card_create', args=[self.deck.id])
        self.preview = reverse('cards:card_draft_preview', args=[self.deck.id])

    def test_default_and_blank_hint_have_no_display(self):
        card = Card.objects.create(deck=self.deck, front='Q',back='A')
        self.assertEqual(card.hint, '')
        self.assertFalse(render_card_face(card,'front').hint_html)
        card.hint='  \n '
        self.assertFalse(render_card_face(card,'front').hint_html)

    def test_rendering_is_front_only_and_follows_format(self):
        card = Card(deck=self.deck,front='Q',back='A',hint='**Cue** <script>alert(1)</script>',content_format='plaintext')
        self.assertIn('**Cue** &lt;script&gt;', render_card_face(card,'front').hint_html)
        self.assertFalse(render_card_face(card,'back').hint_html)
        card.content_format='markdown'
        card.hint='**Cue** \\(x_i\\)\n\n```mermaid\nflowchart TD\nA --> B\n```\n<script>bad</script>'
        rendered = render_card_face(card,'front').hint_html
        self.assertIn('<strong>Cue</strong>', rendered)
        self.assertIn('arithmatex', rendered)
        self.assertIn('data-mermaid="pending"', rendered)
        self.assertNotIn('<script>', rendered)

    def test_both_save_intents_persist_hint_and_edit_can_remove(self):
        for intent in ['save','save_add_another']:
            response = self.client.post(self.create, self.payload | {'intent':intent}, **EDITOR)
            self.assertEqual(response['X-Card-Saved'],'true')
            self.assertEqual(response['X-Card-Continue'],str(intent=='save_add_another').lower())
        self.assertEqual(Card.objects.filter(hint='Think in layers.').count(),2)
        card=self.deck.cards.first()
        card.times_reviewed=4;card.times_correct=3;card.times_wrong=1;card.save()
        response=self.client.post(reverse('cards:card_edit',args=[self.deck.id,card.id]),self.payload|{'hint':''},**EDITOR)
        self.assertEqual(response.status_code,200)
        card.refresh_from_db();self.assertEqual(card.hint,'');self.assertEqual(card.times_reviewed,4)

    def test_invalid_save_does_not_replace_or_persist_draft(self):
        response=self.client.post(self.create,self.payload|{'front':''},**EDITOR)
        self.assertEqual(response.status_code,422)
        self.assertNotContains(response,'<form',status_code=422)
        self.assertEqual(Card.objects.count(),0)

    def test_draft_preview_incomplete_has_collapsed_hint_and_no_persistence(self):
        response=self.client.post(self.preview,self.payload|{'front':'','back':''},**EDITOR)
        self.assertContains(response,'data-hint-hidden="true"')
        self.assertContains(response,'aria-hidden="true"')
        self.assertContains(response,'inert')
        self.assertContains(response,'x-show="shown" x-cloak')
        self.assertContains(response,'Think in layers.')
        self.assertContains(response,'Show hint')
        self.assertEqual(Card.objects.count(),0)
        self.assertNotIn('review_session',self.client.session)

    def test_authoring_hint_types_and_normalization(self):
        values=[None,'','  ',' cue ',0,False,{},[]]
        cards=[{'front':'Q','back':'A','hint':value} for value in values]
        cards.append({'front':'Q','back':'A'})
        result=parse_authoring_json_cards({'schema':'flashcram.cards.v1','cards':cards}, self.user)
        self.assertEqual([c.hint for c in result.cards],['','','','cue',''])
        self.assertEqual(result.skipped_count,4)

    def test_bulk_and_new_deck_import_hint(self):
        payload=json.dumps({'schema':'flashcram.cards.v1','deck':'Hint import','cards':[{'front':'Q','back':'A','hint':'Cue','format':'markdown'}]})
        for url, data in [(reverse('cards:bulk_import'),{'intent':'json_confirm'}),(reverse('cards:deck_create'),{'name':'Hint new deck'})]:
            response=self.client.post(url,data|{'authoring_json_text':payload})
            self.assertEqual(response.status_code,302)
        self.assertEqual(Card.objects.filter(hint='Cue').count(),2)

    def test_copy_backup_roundtrip_and_old_backup_default(self):
        card=Card.objects.create(deck=self.deck,front='Q',back='A',hint='**Cue**')
        target=create_deck(name='Target')
        copy_cards_to_deck([card],target)
        self.assertEqual(target.cards.get().hint,'**Cue**')
        backup=export_backup(self.user)
        Card.objects.update(hint='Changed')
        import_backup(backup,self.user)
        self.assertTrue(all(c.hint=='**Cue**' for c in Card.objects.all()))
        for deck in backup['decks']:
            for saved in deck['cards']: saved.pop('hint')
        import_backup(backup,self.user)
        self.assertFalse(Card.objects.exclude(hint='').exists())

    def test_review_editor_updates_hint_without_changing_queue(self):
        card=Card.objects.create(deck=self.deck,front='Q',back='A')
        self.client.get(reverse('cards:review_start',args=[self.deck.id]))
        before=dict(self.client.session)
        response=self.client.get(reverse('cards:review_edit'))
        self.assertContains(response,'name="hint"')
        response=self.client.post(reverse('cards:review_edit'),self.payload)
        self.assertContains(response,'data-hint')
        card.refresh_from_db();self.assertEqual(card.hint,self.payload['hint']);self.assertEqual(card.times_reviewed,0)
        self.assertEqual(dict(self.client.session),before)

    def test_ownership_and_list_summary(self):
        card=Card.objects.create(deck=self.deck,front='Q',back='A',hint='Private cue')
        response=self.client.get(reverse('cards:deck_detail',args=[self.deck.id]))
        self.assertNotContains(response,'Private cue')
        self.client.force_login(test_user('other'))
        self.assertEqual(self.client.post(self.preview,self.payload).status_code,404)
        self.assertEqual(self.client.post(reverse('cards:card_edit',args=[self.deck.id,card.id]),self.payload).status_code,404)

    def test_hint_editor_has_shared_toolbar_and_expansion(self):
        card=Card.objects.create(deck=self.deck,front='Q',back='A',hint='Cue')
        response=self.client.get(reverse('cards:card_edit',args=[self.deck.id,card.id]),**EDITOR)
        self.assertContains(response,'Hint bold')
        self.assertContains(response,'x-ref="hintInput"')
        self.assertContains(response,'x-ref="hintOptions" open')
