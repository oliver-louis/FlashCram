import json

from django import forms

from .models import Card, Category, Deck, Settings
from .services import (
    ImageProcessingError,
    categories_queryset,
    decks_queryset,
    get_settings,
    is_authenticated_user,
    normalize_tags,
    parse_authoring_json_cards,
    process_image_upload,
)


def json_file_widget():
    return forms.ClearableFileInput(
        attrs={
            "accept": "application/json,.json",
            "class": "file-input file-input-bordered h-14 w-full rounded-2xl",
            "x-ref": "jsonFileInput",
            "@change": "loadFile($event)",
        }
    )


def json_text_widget():
    return forms.Textarea(
        attrs={
            "class": "textarea textarea-bordered min-h-72 w-full rounded-2xl font-mono text-sm",
            "rows": 14,
            "x-ref": "jsonTextInput",
            "x-model": "jsonText",
        }
    )


class DeckForm(forms.ModelForm):
    category_name = forms.CharField(
        required=False,
        label="Category",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered h-14 w-full rounded-2xl",
                "placeholder": "No category",
                "autocomplete": "off",
                "x-model": "categoryQuery",
                "@focus": "categoryOpen = true",
                "@input": "categoryOpen = true",
                "@keydown.enter": "categoryOpen = false",
                "@blur": "setTimeout(() => categoryOpen = false, 120)",
            }
        ),
    )

    class Meta:
        model = Deck
        fields = [
            "name",
            "description",
            "category_name",
            "is_pinned",
            "is_favorite",
            "show_tags_in_review",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-bordered h-14 w-full rounded-2xl"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered min-h-28 w-full rounded-2xl", "rows": 3}
            ),
            "is_pinned": forms.CheckboxInput(attrs={"class": "toggle toggle-primary"}),
            "is_favorite": forms.CheckboxInput(attrs={"class": "toggle toggle-secondary"}),
            "show_tags_in_review": forms.CheckboxInput(attrs={"class": "toggle toggle-primary"}),
        }
        labels = {
            "category_name": "Category",
            "is_pinned": "Pin this deck",
            "is_favorite": "Favourite this deck",
            "show_tags_in_review": "Show tags by default during review",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.category:
            self.fields["category_name"].initial = self.instance.category.name

    def clean_category_name(self):
        return (self.cleaned_data.get("category_name") or "").strip()

    def save(self, commit=True):
        deck = super().save(commit=False)
        if self.user is not None and not deck.owner_id:
            deck.owner = self.user
        category_name = self.cleaned_data.get("category_name", "")
        if category_name and is_authenticated_user(self.user):
            category = Category.objects.filter(owner=self.user, name__iexact=category_name).first()
            if category is None:
                category = Category.objects.create(owner=self.user, name=category_name)
            deck.category = category
        elif category_name:
            category = Category.objects.filter(name__iexact=category_name).first()
            if category is not None:
                deck.category = category
        else:
            deck.category = None
        if commit:
            deck.save()
        return deck


class DeckCreateForm(DeckForm):
    authoring_json_file = forms.FileField(
        required=False,
        label="JSON file",
        widget=json_file_widget(),
    )
    authoring_json_text = forms.CharField(
        required=False,
        label="JSON text",
        widget=json_text_widget(),
    )

    class Meta(DeckForm.Meta):
        fields = [*DeckForm.Meta.fields, "authoring_json_file", "authoring_json_text"]

    def __init__(self, *args, **kwargs):
        self.authoring_result = None
        super().__init__(*args, **kwargs)
        self.fields["name"].required = False

    def clean(self):
        cleaned_data = super().clean()
        name = (cleaned_data.get("name") or "").strip()
        payload = (cleaned_data.get("authoring_json_text") or "").strip()

        if payload:
            try:
                self.authoring_result = parse_authoring_json_cards(payload, self.user)
            except ValueError as exc:
                self.add_error("authoring_json_text", str(exc))
                return cleaned_data

        if not name and self.authoring_result and self.authoring_result.deck_name:
            cleaned_data["name"] = self.authoring_result.deck_name
        elif not name:
            self.add_error("name", "Enter a deck name or upload JSON with a deck name.")
        return cleaned_data


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
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["tags_text"].initial = ", ".join(self.instance.tags or [])
        else:
            self.fields["content_format"].initial = get_settings(self.user).default_content_format
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
        return get_settings(self.user).default_content_format

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
        widget=json_file_widget(),
    )
    authoring_json_text = forms.CharField(
        required=False,
        widget=json_text_widget(),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["deck"].queryset = decks_queryset(user)


class JsonImportForm(forms.Form):
    backup_json_file = forms.FileField(
        required=False,
        label="Backup JSON file",
        widget=json_file_widget(),
    )
    backup_json_text = forms.CharField(
        required=False,
        label="Backup JSON text",
        widget=json_text_widget(),
    )
    backup_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def clean(self):
        cleaned_data = super().clean()
        backup_json_text = (cleaned_data.get("backup_json_text") or "").strip()
        legacy_backup_json = (cleaned_data.get("backup_json") or "").strip()
        if not backup_json_text and legacy_backup_json:
            cleaned_data["backup_json_text"] = legacy_backup_json
        if not (cleaned_data.get("backup_json_text") or "").strip():
            self.add_error("backup_json_text", "Upload a backup JSON file or paste backup JSON before importing.")
        return cleaned_data
