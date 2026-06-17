import json

from django import forms

from .models import Card, Deck, Settings
from .services import ImageProcessingError, get_settings, normalize_tags, process_image_upload


class DeckForm(forms.ModelForm):
    class Meta:
        model = Deck
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-bordered h-14 w-full rounded-2xl"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered min-h-28 w-full rounded-2xl", "rows": 3}
            ),
        }


class CardForm(forms.ModelForm):
    image_upload = forms.FileField(
        required=False,
        label="Image",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": "image/png,image/jpeg,image/webp,image/gif",
                "class": "file-input file-input-bordered h-14 w-full rounded-2xl",
                "x-ref": "imageInput",
                "@change": "imageName = $event.target.files[0]?.name || imageName",
            }
        ),
    )
    remove_image = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
    )
    tags_text = forms.CharField(
        required=False,
        label="Tags",
        help_text="Separate multiple tags with commas or spaces.",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered h-14 w-full rounded-2xl",
                "autocomplete": "off",
                "x-ref": "tagsInput",
            }
        ),
    )

    class Meta:
        model = Card
        fields = ["front", "back", "content_format", "tags_text", "status", "image_face"]
        widgets = {
            "front": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered min-h-36 w-full rounded-2xl",
                    "rows": 5,
                    "@focus": "focusedFace = 'front'",
                    "x-ref": "frontInput",
                }
            ),
            "back": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered min-h-36 w-full rounded-2xl",
                    "rows": 5,
                    "@focus": "focusedFace = 'back'",
                    "x-ref": "backInput",
                }
            ),
            "content_format": forms.Select(attrs={"class": "select select-bordered h-14 w-full rounded-2xl"}),
            "status": forms.Select(attrs={"class": "select select-bordered h-14 w-full rounded-2xl"}),
            "image_face": forms.Select(attrs={"class": "select select-bordered h-14 w-full rounded-2xl"}),
        }

    def __init__(self, *args, **kwargs):
        preview_url = kwargs.pop("preview_url", "")
        card_id = kwargs.pop("card_id", "")
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["tags_text"].initial = ", ".join(self.instance.tags or [])
        else:
            self.fields["content_format"].initial = get_settings().default_content_format
        self.fields["content_format"].required = False
        self.fields["image_face"].required = False
        if preview_url:
            for face in ("front", "back"):
                preview_values = {"face": face}
                if card_id:
                    preview_values["card_id"] = str(card_id)
                self.fields[face].widget.attrs.update(
                    {
                        "hx-post": preview_url,
                        "hx-trigger": "input changed delay:500ms",
                        "hx-target": f"#{face}-preview",
                        "hx-swap": "outerHTML",
                        "hx-include": 'input[name="content_format"]:checked',
                        "hx-vals": json.dumps(preview_values),
                    }
                )

    def clean_content_format(self):
        value = self.cleaned_data.get("content_format")
        if value:
            return value
        if self.instance and self.instance.pk:
            return self.instance.content_format
        return get_settings().default_content_format

    def clean_image_face(self):
        value = self.cleaned_data.get("image_face")
        if value:
            return value
        if self.instance and self.instance.pk:
            return self.instance.image_face
        return Card.ImageFace.BACK

    def clean_image_upload(self):
        uploaded = self.cleaned_data.get("image_upload")
        if not uploaded:
            return None
        try:
            return process_image_upload(uploaded)
        except ImageProcessingError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def save(self, commit=True):
        card = super().save(commit=False)
        card.tags = normalize_tags(self.cleaned_data.get("tags_text"))
        if self.cleaned_data.get("remove_image"):
            card.image = None
            card.image_mime = ""
        processed_image = self.cleaned_data.get("image_upload")
        if processed_image:
            card.image, card.image_mime = processed_image
        if commit:
            card.save()
        return card


class SettingsForm(forms.ModelForm):
    class Meta:
        model = Settings
        fields = ["theme", "weak_min_wrong", "weak_min_ratio", "show_less_weight", "default_content_format"]
        widgets = {
            "theme": forms.Select(attrs={"class": "select select-bordered h-14 w-full rounded-2xl"}),
            "weak_min_wrong": forms.NumberInput(attrs={"class": "input input-bordered h-14 w-full rounded-2xl", "min": 0}),
            "weak_min_ratio": forms.NumberInput(
                attrs={"class": "input input-bordered h-14 w-full rounded-2xl", "min": 0, "max": 1, "step": "0.01"}
            ),
            "show_less_weight": forms.NumberInput(
                attrs={"class": "input input-bordered h-14 w-full rounded-2xl", "min": 0, "step": "0.01"}
            ),
            "default_content_format": forms.Select(attrs={"class": "select select-bordered h-14 w-full rounded-2xl"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_content_format"].required = False

    def clean_default_content_format(self):
        value = self.cleaned_data.get("default_content_format")
        if value:
            return value
        if self.instance and self.instance.pk:
            return self.instance.default_content_format
        return Settings.DefaultContentFormat.PLAINTEXT


class BulkImportForm(forms.Form):
    deck = forms.ModelChoiceField(
        queryset=Deck.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "select select-bordered h-14 w-full rounded-2xl"}),
    )
    new_deck_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input input-bordered h-14 w-full rounded-2xl"}),
    )
    text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "textarea textarea-bordered min-h-72 w-full rounded-2xl", "rows": 14})
    )
    authoring_json_file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                "accept": "application/json,.json",
                "class": "file-input file-input-bordered h-14 w-full rounded-2xl",
            }
        ),
    )
    authoring_json_text = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "textarea textarea-bordered min-h-72 w-full rounded-2xl font-mono text-sm", "rows": 14}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["deck"].queryset = Deck.objects.all().order_by("created_at", "name")


class JsonImportForm(forms.Form):
    backup_json = forms.CharField(
        widget=forms.Textarea(attrs={"class": "textarea textarea-bordered min-h-72 w-full rounded-2xl", "rows": 14})
    )
