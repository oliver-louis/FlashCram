from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from cards.models import Card, Category, Deck, Settings
from cards.services import export_backup, get_settings, import_backup
from cards.tests.utils import create_category, create_deck, test_user
from flashcram.auth import FlashCramOIDCAuthenticationBackend


HTMX = {"HTTP_HX_REQUEST": "true"}


class MultiUserScopingTests(TestCase):
    def setUp(self):
        self.user_a = test_user("user-a")
        self.user_b = test_user("user-b")
        self.client.force_login(self.user_a)

    def test_creating_deck_sets_request_user_owner(self):
        response = self.client.post(
            reverse("cards:deck_create"),
            {"name": "Owned", "description": ""},
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(Deck.objects.get(name="Owned").owner, self.user_a)

    def test_user_cannot_read_or_modify_another_users_deck_or_card(self):
        other_deck = create_deck(name="Private", owner=self.user_b)
        other_card = Card.objects.create(deck=other_deck, front="Secret", back="Back")

        self.assertEqual(
            self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": other_deck.id})).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("cards:deck_edit", kwargs={"deck_id": other_deck.id}),
                {"name": "Stolen", "description": ""},
                **HTMX,
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("cards:card_edit", kwargs={"deck_id": other_deck.id, "card_id": other_card.id}),
                {"front": "Changed", "back": "Changed", "status": Card.Status.NORMAL},
                **HTMX,
            ).status_code,
            404,
        )
        other_deck.refresh_from_db()
        other_card.refresh_from_db()
        self.assertEqual(other_deck.name, "Private")
        self.assertEqual(other_card.front, "Secret")

    def test_home_and_marked_cards_only_show_current_user_data(self):
        own_deck = create_deck(name="Mine", owner=self.user_a)
        other_deck = create_deck(name="Theirs", owner=self.user_b)
        Card.objects.create(deck=own_deck, front="Own marked", back="Back", is_marked=True)
        Card.objects.create(deck=other_deck, front="Other marked", back="Back", is_marked=True)

        home = self.client.get(reverse("cards:home"))
        marked = self.client.get(reverse("cards:marked_cards"))

        self.assertContains(home, "Mine")
        self.assertNotContains(home, "Theirs")
        self.assertContains(marked, "Own marked")
        self.assertNotContains(marked, "Other marked")

    def test_per_user_settings_are_isolated_in_views(self):
        settings_a = get_settings(self.user_a)
        settings_b = get_settings(self.user_b)
        settings_a.weak_min_wrong = 9
        settings_a.save()

        settings_b.refresh_from_db()
        self.assertEqual(settings_b.weak_min_wrong, 2)

        self.client.force_login(self.user_b)
        response = self.client.get(reverse("cards:settings"))
        self.assertContains(response, 'value="2"')

    def test_backup_export_import_is_scoped_and_rejects_cross_owner_ids(self):
        own_deck = create_deck(name="Mine", owner=self.user_a)
        other_deck = create_deck(name="Theirs", owner=self.user_b)
        Card.objects.create(deck=own_deck, front="Own", back="Back")
        Card.objects.create(deck=other_deck, front="Other", back="Back")

        payload = export_backup(self.user_a)
        self.assertEqual([deck["name"] for deck in payload["decks"]], ["Mine"])

        payload["decks"][0]["id"] = str(other_deck.id)
        with self.assertRaisesMessage(ValueError, "belongs to another user"):
            import_backup(payload, self.user_a)


class AuthFlowTests(TestCase):
    def test_anonymous_app_request_redirects_to_oidc_login(self):
        response = Client().get(reverse("cards:home"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("oidc_authentication_init"), response["Location"])

    def test_oidc_backend_creates_and_finds_user_from_claims(self):
        backend = FlashCramOIDCAuthenticationBackend()
        claims = {
            "preferred_username": "oliver",
            "email": "oliver@example.com",
            "given_name": "Oliver",
            "family_name": "Student",
            "sub": "authentik-subject",
        }

        user = backend.create_user(claims)
        matches = backend.filter_users_by_claims(claims)

        self.assertEqual(user.username, "oliver")
        self.assertEqual(user.email, "oliver@example.com")
        self.assertEqual(matches.get(), user)


class AssignOrphanDecksCommandTests(TransactionTestCase):
    reset_sequences = True

    def test_assign_orphan_decks_assigns_data_and_legacy_settings(self):
        user = test_user("owner")

        deck_owner_field = Deck._meta.get_field("owner")
        category_owner_field = Category._meta.get_field("owner")
        settings_user_field = Settings._meta.get_field("user")
        nullable_deck_owner = deck_owner_field.clone()
        nullable_category_owner = category_owner_field.clone()
        nullable_settings_user = settings_user_field.clone()
        nullable_deck_owner.remote_field.model = deck_owner_field.remote_field.model
        nullable_category_owner.remote_field.model = category_owner_field.remote_field.model
        nullable_settings_user.remote_field.model = settings_user_field.remote_field.model
        for old_field, new_field in (
            (deck_owner_field, nullable_deck_owner),
            (category_owner_field, nullable_category_owner),
            (settings_user_field, nullable_settings_user),
        ):
            new_field.model = old_field.model
            new_field.name = old_field.name
            new_field.column = old_field.column
            new_field.attname = old_field.attname
            new_field.concrete = old_field.concrete
            new_field.remote_field.field_name = old_field.remote_field.field_name
        nullable_deck_owner.null = True
        nullable_category_owner.null = True
        nullable_settings_user.null = True

        with connection.schema_editor() as schema_editor:
            schema_editor.alter_field(Deck, deck_owner_field, nullable_deck_owner)
            schema_editor.alter_field(Category, category_owner_field, nullable_category_owner)
            schema_editor.alter_field(Settings, settings_user_field, nullable_settings_user)
        try:
            category = Category.objects.create(owner=None, name="Legacy")
            deck = Deck.objects.create(owner=None, name="Legacy deck", category=category)
            legacy_settings = Settings.objects.create(user=None, weak_min_wrong=6)

            call_command("assign_orphan_decks", user.username, verbosity=0)

            deck.refresh_from_db()
            category.refresh_from_db()
            self.assertEqual(deck.owner, user)
            self.assertEqual(category.owner, user)
            self.assertFalse(Settings.objects.filter(pk=legacy_settings.pk, user__isnull=True).exists())
            self.assertEqual(Settings.objects.get(user=user).weak_min_wrong, 6)
        finally:
            with connection.schema_editor() as schema_editor:
                schema_editor.alter_field(Deck, nullable_deck_owner, deck_owner_field)
                schema_editor.alter_field(Category, nullable_category_owner, category_owner_field)
                schema_editor.alter_field(Settings, nullable_settings_user, settings_user_field)
