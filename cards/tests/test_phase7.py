from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, SESSION_KEY, get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from cards.models import Card, Deck
from cards.tests.utils import create_deck, test_user
from flashcram.auth import FlashCramOIDCAuthenticationBackend


HTMX = {"HTTP_HX_REQUEST": "true"}


class LoginPageTests(TestCase):
    def test_login_page_renders_local_form_and_authentik_button(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, "Sign in with Authentik")
        self.assertContains(response, reverse("oidc_authentication_init"))

    def test_protected_page_redirects_to_login_not_oidc(self):
        response = self.client.get(reverse("cards:home"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(f"{reverse('login')}?next="))
        self.assertNotIn(reverse("oidc_authentication_init"), response["Location"])

    def test_local_user_can_log_in_with_valid_credentials(self):
        get_user_model().objects.create_user(username="local", password="correct-password")

        response = self.client.post(
            reverse("login"),
            {"username": "local", "password": "correct-password"},
        )

        self.assertRedirects(response, reverse("cards:home"))
        self.assertEqual(str(self.client.session[SESSION_KEY]), str(get_user_model().objects.get(username="local").pk))

    def test_local_login_rejects_invalid_credentials(self):
        get_user_model().objects.create_user(username="local", password="correct-password")

        response = self.client.post(
            reverse("login"),
            {"username": "local", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct username and password")
        self.assertNotIn(SESSION_KEY, self.client.session)

    @override_settings(
        OIDC_RP_CLIENT_ID="flashcram",
        OIDC_OP_AUTHORIZATION_ENDPOINT="https://auth.example.com/application/o/flashcram/authorize/",
    )
    def test_authentik_button_initiates_oidc_flow(self):
        response = self.client.get(reverse("oidc_authentication_init"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(settings.OIDC_OP_AUTHORIZATION_ENDPOINT))

    def test_oidc_backend_creates_user_without_linking_local_password_account(self):
        get_user_model().objects.create_user(
            username="oliver",
            email="oliver@example.com",
            password="local-password",
        )
        backend = FlashCramOIDCAuthenticationBackend()
        claims = {
            "preferred_username": "oliver",
            "email": "oliver@example.com",
            "given_name": "Oliver",
            "family_name": "Student",
            "sub": "authentik-subject",
        }

        self.assertFalse(backend.filter_users_by_claims(claims).exists())
        oidc_user = backend.create_user(claims)
        matches = backend.filter_users_by_claims(claims)

        self.assertEqual(oidc_user.username, "oliver-2")
        self.assertFalse(oidc_user.has_usable_password())
        self.assertEqual(matches.get(), oidc_user)


class LogoutAndSettingsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="local",
            email="local@example.com",
            password="correct-password",
        )
        self.client.login(username="local", password="correct-password")

    def test_logout_post_clears_session_and_redirects_to_login(self):
        self.assertIn(SESSION_KEY, self.client.session)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn(SESSION_KEY, self.client.session)
        protected = self.client.get(reverse("cards:home"))
        self.assertTrue(protected["Location"].startswith(f"{reverse('login')}?next="))

    def test_logout_get_is_not_allowed(self):
        response = self.client.get(reverse("logout"))

        self.assertEqual(response.status_code, 405)
        self.assertIn(SESSION_KEY, self.client.session)

    def test_settings_page_shows_account_settings_and_logout_button(self):
        response = self.client.get(reverse("cards:settings"))

        self.assertContains(response, "Account settings")
        self.assertContains(response, "local")
        self.assertContains(response, "local@example.com")
        self.assertContains(response, f'action="{reverse("logout")}"')
        self.assertContains(response, "Log out")


class SessionLifetimeTests(TestCase):
    def test_session_lifetime_defaults_to_five_non_rolling_days(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 5 * 86400)
        self.assertFalse(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertFalse(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)


class LocalLoginIsolationTests(TestCase):
    def test_local_login_user_cannot_access_another_users_objects(self):
        User = get_user_model()
        user_a = User.objects.create_user(username="local-a", password="password-a")
        user_b = User.objects.create_user(username="local-b", password="password-b")
        deck_a = create_deck(name="Mine", owner=user_a)
        deck_b = create_deck(name="Theirs", owner=user_b)
        card_b = Card.objects.create(deck=deck_b, front="Secret", back="Back")

        self.client.login(username="local-a", password="password-a")

        self.assertEqual(self.client.get(reverse("cards:deck_detail", kwargs={"deck_id": deck_b.id})).status_code, 404)
        self.assertEqual(
            self.client.post(
                reverse("cards:card_edit", kwargs={"deck_id": deck_b.id, "card_id": card_b.id}),
                {"front": "Changed", "back": "Changed", "status": Card.Status.NORMAL},
                **HTMX,
            ).status_code,
            404,
        )
        response = self.client.get(reverse("cards:home"))
        self.assertContains(response, "Mine")
        self.assertNotContains(response, "Theirs")

    def test_deck_create_owner_is_local_login_user(self):
        get_user_model().objects.create_user(username="local", password="correct-password")
        self.client.login(username="local", password="correct-password")

        response = self.client.post(reverse("cards:deck_create"), {"name": "Owned"}, **HTMX)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(Deck.objects.get(name="Owned").owner.username, "local")
