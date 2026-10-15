from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from apps.semantic.catalogue import LEVELS, RESOURCE_TYPES

LANGUAGES = [("fr", "Français"), ("en", "Anglais"), ("ar", "Arabe"), ("de", "Allemand"), ("es", "Espagnol")]


class StaffAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Identifiant", widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "Votre identifiant", "autofocus": True}))
    password = forms.CharField(label="Mot de passe", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Votre mot de passe"}))

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError("Ce compte n'a pas accès à l'espace de gestion.", code="not_staff")


class EntityForm(forms.Form):
    version = forms.CharField(widget=forms.HiddenInput)
    title = forms.CharField(label="Titre", max_length=180, widget=forms.TextInput(attrs={"placeholder": "Un titre clair et précis", "data-title-input": "", "wide": True}))
    description = forms.CharField(label="Description", max_length=5000, required=False, widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Présentez le contenu et son objectif…", "wide": True}))

    def __init__(self, *args, snapshot, kind, record=None, **kwargs):
        if kind == "ressources" and args and args[0] is not None:
            bound_data = args[0].copy()
            if bound_data.get("source") == "file":
                bound_data["url"] = ""
            args = (bound_data, *args[1:])
        initial = dict(kwargs.pop("initial", {}))
        initial["version"] = snapshot.version
        if record:
            initial.update({key: record[key] for key in ["title", "description", "language", "duration", "level", "resource_type", "url"]})
            for field in ["skills", "required_skills", "prerequisites", "resources", "paths", "courses"]:
                initial[field] = [row["id"] for row in record[field]]
            initial["source"] = "file" if record["is_local_pdf"] else "url"
            if kind == "ressources":
                initial["courses"] = [row["id"] for row in record["used_by"]]
                if record["is_local_pdf"]:
                    initial["url"] = ""
        super().__init__(*args, initial=initial, **kwargs)
        self.snapshot, self.record, self.kind = snapshot, record, kind

        def multiple(name, label, target, *, required=False, help_text="", exclude=None):
            choices = [(row["id"], row["title"]) for row in snapshot.all(target) if row["id"] != exclude]
            self.fields[name] = forms.MultipleChoiceField(
                label=label, choices=choices, required=required, help_text=help_text,
                widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-grid", "wide": True}),
            )

        groups = []
        if kind == "competences":
            self.fields["title"].label = "Nom de la compétence"
            self.fields["title"].widget.attrs["placeholder"] = "Ex. Programmation Python"
            groups = [("L'essentiel", "Une compétence précise rend les cours plus faciles à relier.", ["title", "description"])]
        elif kind == "cours":
            self.fields["description"].required = True
            self.fields["language"] = forms.ChoiceField(label="Langue du cours", choices=LANGUAGES, initial="fr")
            self.fields["duration"] = forms.IntegerField(label="Durée estimée (minutes)", min_value=1, max_value=100000, initial=60, widget=forms.NumberInput(attrs={"placeholder": "120"}))
            self.fields["level"] = forms.ChoiceField(label="Niveau", choices=list(LEVELS.items()), initial="Debutant")
            multiple("skills", "Compétences enseignées", "competences", required=True, help_text="Sélectionnez au moins une compétence que ce cours permet d'acquérir.")
            multiple("required_skills", "Compétences requises", "competences", help_text="Les connaissances nécessaires avant de commencer. Facultatif.")
            multiple("prerequisites", "Cours prérequis", "cours", exclude=record["id"] if record else None, help_text="Choisissez les cours à suivre auparavant. Les boucles sont refusées.")
            multiple("resources", "Supports pédagogiques", "ressources", help_text="Vous pourrez aussi ajouter des supports après la création du cours.")
            multiple("paths", "Parcours associés", "parcours", help_text="Un même cours peut appartenir à plusieurs parcours.")
            groups = [
                ("Présentation du cours", "Les informations que les apprenants découvriront.", ["title", "description", "language", "duration", "level"]),
                ("Compétences & prérequis", "Définissez les acquis visés et le point de départ.", ["skills", "required_skills", "prerequisites"]),
                ("Supports & parcours", "Reliez ce cours au reste du catalogue.", ["resources", "paths"]),
            ]
        elif kind == "ressources":
            self.fields["resource_type"] = forms.ChoiceField(label="Type de support", choices=list(RESOURCE_TYPES.items()), initial="PageWeb")
            self.fields["language"] = forms.ChoiceField(label="Langue du support", choices=LANGUAGES, initial="fr")
            self.fields["source"] = forms.ChoiceField(label="Source du contenu", choices=[("url", "Un lien web"), ("file", "Un fichier PDF")], initial="url", widget=forms.RadioSelect(attrs={"class": "source-options", "wide": True}))
            self.fields["url"] = forms.URLField(label="Adresse du support", required=False, max_length=2000, validators=[URLValidator(schemes=["http", "https"])], widget=forms.URLInput(attrs={"placeholder": "https://…", "wide": True}))
            self.fields["file"] = forms.FileField(label="Fichier PDF", required=False, help_text=f"PDF uniquement · {settings.PDF_UPLOAD_MAX_MB} Mo maximum.", widget=forms.FileInput(attrs={"accept": ".pdf,application/pdf", "wide": True}))
            multiple("courses", "Cours associés", "cours", help_text="Ce support peut être partagé entre plusieurs cours.")
            groups = [
                ("Présentation du support", "Un document, une page, une vidéo ou un exercice.", ["title", "description", "resource_type", "language"]),
                ("Contenu", "Ajoutez un lien ou téléversez votre propre PDF.", ["source", "url", "file"]),
                ("Cours associés", "Retrouvez ce support directement depuis les cours choisis.", ["courses"]),
            ]
        elif kind == "parcours":
            self.fields["description"].required = True
            self.fields["title"].widget.attrs["placeholder"] = "Ex. De Python au développement web"
            multiple("courses", "Cours du parcours", "cours", required=True, help_text="Au moins un cours. Les prérequis définissent les liens pédagogiques.")
            groups = [
                ("Objectif du parcours", "Donnez une direction à cet ensemble de cours.", ["title", "description"]),
                ("Composition", "Sélectionnez les cours qui contribuent à cet objectif.", ["courses"]),
            ]
        self.sections = [{"title": title, "description": description, "fields": [self[name] for name in names]} for title, description, names in groups]

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if self.kind == "competences":
            for record in self.snapshot.all("competences"):
                if record["title"].casefold() == title.casefold() and (not self.record or record["id"] != self.record["id"]):
                    raise ValidationError("Cette compétence existe déjà dans le catalogue.")
        return title

    def clean_file(self):
        if self.data.get("source") != "file":
            return None
        upload = self.cleaned_data.get("file")
        if upload:
            if Path(upload.name).suffix.lower() != ".pdf":
                raise ValidationError("Choisissez un document au format PDF.")
            if upload.size > settings.PDF_UPLOAD_MAX_MB * 1024 * 1024:
                raise ValidationError(f"Le fichier dépasse la limite de {settings.PDF_UPLOAD_MAX_MB} Mo.")
            header = upload.read(5)
            upload.seek(0)
            if header != b"%PDF-":
                raise ValidationError("Le contenu du fichier ne correspond pas à un PDF.")
        return upload

    def clean(self):
        data = super().clean()
        if self.kind == "ressources":
            if data.get("source") == "url" and not data.get("url"):
                self.add_error("url", "Indiquez l'adresse du support.")
            if data.get("source") == "file":
                if not data.get("file") and not (self.record and self.record["is_local_pdf"]):
                    self.add_error("file", "Sélectionnez un fichier PDF.")
                data["resource_type"] = "DocumentPDF"
        return data
