from .services import get_settings


def flashcram_settings(request):
    return {"settings": get_settings()}
