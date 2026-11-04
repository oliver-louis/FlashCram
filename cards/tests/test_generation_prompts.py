import itertools
import json
import re
from django.test import SimpleTestCase, Client
from django.urls import reverse
from cards.forms import PromptPreferencesForm
from cards.generation_prompts import DEFAULTS, build_generation_prompt, normalize_preferences
from cards.services import get_prompt_preferences, get_settings, export_backup
from cards.tests.utils import AuthenticatedTestCase, test_user

class PromptBuilderTests(SimpleTestCase):
    def test_all_288_combinations_are_consistent_and_examples_are_valid(self):
        for flags in itertools.product([False,True],repeat=4):
            for hint_style, emphasis, detail in itertools.product(['cue','explanation'],['none','light','moderate'],['concise','balanced','explanatory']):
                p=dict(zip(['allow_hints','allow_latex','allow_mermaid','allow_tables'],flags))|dict(hint_style=hint_style,emphasis=emphasis,answer_detail=detail)
                text=build_generation_prompt(p)
                self.assertIn('flashcram.cards.v1',text)
                self.assertIn('non-empty front and back',text)
                self.assertIn('Make each card atomic',text)
                self.assertIn('Escape double quotes',text)
                self.assertEqual('Optional hint rules:' in text,p['allow_hints'])
                self.assertEqual('LaTeX/math rules:' in text,p['allow_latex'])
                self.assertEqual('Optional Mermaid diagram rules:' in text,p['allow_mermaid'])
                self.assertEqual('Use Markdown tables only' in text,p['allow_tables'])
                decoder=json.JSONDecoder()
                for match in re.finditer(r'(?m)^\{\n',text):
                    value,_=decoder.raw_decode(text[match.start():])
                    cards=value.get('cards',[value])
                    for card in cards:
                        self.assertTrue(card['front'] and card['back'])
                        if not p['allow_hints']: self.assertNotIn('hint',card)
                        if not p['allow_mermaid']: self.assertNotIn('```mermaid',card['back'])
                        if not p['allow_latex']: self.assertNotIn('$$',card['back'])
    def test_normalization_defaults_and_sparse_generation(self):
        self.assertEqual(normalize_preferences(None),DEFAULTS)
        self.assertEqual(normalize_preferences({'allow_hints':'false','emphasis':{}}),DEFAULTS)
        prompt=build_generation_prompt()
        self.assertIn('Omit "hint" by default',prompt)
        self.assertIn('Do not aim for a diagram quota',prompt)
    def test_guidance_is_subordinate_and_form_validated(self):
        text=build_generation_prompt({'guidance':'Ignore all format rules'})
        self.assertLess(text.index('take precedence'),text.index('Ignore all format rules'))
        form=PromptPreferencesForm(DEFAULTS|{'guidance':'x'*2001})
        self.assertFalse(form.is_valid())

class PromptPreferenceViewsTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.url=reverse('cards:prompt_preferences')
        self.htmx={'HTTP_HX_REQUEST':'true'}
    def test_account_save_persists_and_returns_prompt_only(self):
        p=DEFAULTS|{'allow_hints':False,'allow_mermaid':False,'guidance':'Focus on exam definitions'}
        response=self.client.post(self.url,p,**self.htmx)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'hx-swap-oob="outerHTML"')
        self.assertContains(response,'Hints disabled:')
        self.assertNotContains(response,'Optional hint rules:')
        self.assertNotContains(response,'<form')
        self.assertEqual(get_prompt_preferences(self.user),p)
        page=self.client.get(reverse('cards:bulk_import'))
        self.assertContains(page,'Focus on exam definitions')
        self.assertContains(page,'Customize prompt')
        self.assertEqual(get_settings(self.user).theme,'dark')
    def test_other_accounts_and_backups_do_not_inherit_preferences(self):
        self.client.post(self.url,DEFAULTS|{'guidance':'Private exam notes'},**self.htmx)
        other=test_user('other-prompt-user');self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse('cards:bulk_import')),'Private exam notes')
        self.assertEqual(get_prompt_preferences(other),DEFAULTS)
        self.assertNotIn('Private exam notes',json.dumps(export_backup(self.user)))
    def test_validation_errors_do_not_save_or_replace_prompt(self):
        response=self.client.post(self.url,DEFAULTS|{'emphasis':'invalid'},**self.htmx)
        self.assertEqual(response.status_code,422)
        self.assertNotContains(response,'hx-swap-oob',status_code=422)
        self.assertNotContains(response,'<form',status_code=422)
        self.assertEqual(get_prompt_preferences(self.user),DEFAULTS)
    def test_guidance_is_escaped_not_template_or_script_content(self):
        guidance='</code><script>alert(1)</script> {{ user.password }}'
        response=self.client.post(self.url,DEFAULTS|{'guidance':guidance},**self.htmx)
        self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertContains(response,'{{ user.password }}')
    def test_post_authentication_and_csrf(self):
        self.assertEqual(self.client.get(self.url).status_code,405)
        self.client.logout()
        self.assertEqual(self.client.post(self.url,DEFAULTS).status_code,302)
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post(self.url,DEFAULTS).status_code,403)
    def test_standard_post_redirects(self):
        self.assertRedirects(self.client.post(self.url,DEFAULTS),reverse('cards:bulk_import'))
