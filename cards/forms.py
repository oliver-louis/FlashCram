from django import forms

from .models import Card, Deck, Settings
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


class SettingsForm(forms.ModelForm):
    class Meta:
        model = Settings
        fields = ["theme", "weak_min_wrong", "weak_min_ratio", "show_less_weight"]
        widgets = {
            "theme": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "weak_min_wrong": forms.NumberInput(attrs={"class": "input input-bordered w-full", "min": 0}),
            "weak_min_ratio": forms.NumberInput(
                attrs={"class": "input input-bordered w-full", "min": 0, "max": 1, "step": "0.01"}
            ),
            "show_less_weight": forms.NumberInput(
                attrs={"class": "input input-bordered w-full", "min": 0, "step": "0.01"}
            ),
        }


class BulkImportForm(forms.Form):
    deck = forms.ModelChoiceField(
        queryset=Deck.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )
    new_deck_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input input-bordered w-full"}),
    )
    text = forms.CharField(
        widget=forms.Textarea(attrs={"class": "textarea textarea-bordered min-h-72 w-full", "rows": 14})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["deck"].queryset = Deck.objects.all().order_by("created_at", "name")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("deck") and not cleaned.get("new_deck_name"):
            raise forms.ValidationError("Choose a deck or enter a new deck name.")
        return cleaned


class JsonImportForm(forms.Form):
    backup_json = forms.CharField(
        widget=forms.Textarea(attrs={"class": "textarea textarea-bordered min-h-72 w-full", "rows": 14})
    )
