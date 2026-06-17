from django import template

from cards.rendering import card_image_data_uri, plain_text_preview, render_content


register = template.Library()


@register.filter
def render_card_content(value, content_format):
    return render_content(value, content_format)


@register.filter
def card_plain_preview(value, content_format):
    return plain_text_preview(value, content_format)


@register.filter
def image_data_uri(card, face):
    return card_image_data_uri(card, face)
