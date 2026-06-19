from django.contrib.auth import get_user_model
from django.test import TestCase

from cards.models import Category, Deck


def test_user(username="testuser"):
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@example.com"},
    )
    return user


def create_category(name="Category", owner=None, **kwargs):
    return Category.objects.create(owner=owner or test_user(), name=name, **kwargs)


def create_deck(name="Deck", owner=None, **kwargs):
    return Deck.objects.create(owner=owner or test_user(), name=name, **kwargs)


class AuthenticatedTestCase(TestCase):
    def setUp(self):
        self.user = test_user()
        self.client.force_login(self.user)
