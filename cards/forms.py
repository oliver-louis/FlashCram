from django import forms

from .models import Card, Deck
from .services import normalize_tags


class DeckForm(forms.ModelForm):
    class Meta:
        model = Deck
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered min-h-24 w-full", "rows": 3}
            ),
        }


class CardForm(forms.ModelForm):
    tags_text = forms.CharField(
        required=False,
        label="Tags",
        help_text="Separate tags with commas or spaces.",
        widget=forms.TextInput(attrs={"class": "input input-bordered w-full"}),
    )

    class Meta:
        model = Card
        fields = ["front", "back", "tags_text", "status"]
        widgets = {
            "front": forms.Textarea(
                attrs={"class": "textarea textarea-bordered min-h-32 w-full", "rows": 5}
            ),
            "back": forms.Textarea(
                attrs={"class": "textarea textarea-bordered min-h-32 w-full", "rows": 5}
            ),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["tags_text"].initial = ", ".join(self.instance.tags or [])

    def save(self, commit=True):
        card = super().save(commit=False)
        card.tags = normalize_tags(self.cleaned_data.get("tags_text"))
        if commit:
            card.save()
        return card
