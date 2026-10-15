"""Présentation publique du catalogue RDF, sans copie des données métier."""
from functools import wraps
import unicodedata
from urllib.parse import urlsplit

from django.shortcuts import render
from django.urls import reverse

from apps.semantic.catalogue import Catalogue, KINDS
from apps.semantic.services import SemanticStoreError


def folded(value):
    return "".join(char for char in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(char))


def public_view(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except SemanticStoreError:
            return render(request, "core/unavailable.html", status=503)
    return wrapped


def duration_label(minutes):
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02}" if hours and minutes else f"{hours} h" if hours else f"{minutes} min"


class PublicCatalogue:
    def __init__(self):
        self.snapshot = Catalogue().snapshot()
        self.records = {kind: [self.decorate(row) for row in self.snapshot.all(kind)] for kind in KINDS}
        self.by_id = {row["id"]: row for rows in self.records.values() for row in rows}

    def decorate(self, record):
        row = dict(record)
        row["public_url"] = reverse("core:detail", args=[row["kind"], row["id"]])
        row["duration_label"] = duration_label(row["duration"])
        row["language_label"] = {"fr": "Français", "en": "Anglais", "ar": "Arabe"}.get(row["language"], row["language"].upper())
        row["tone"] = sum(ord(char) for char in row["id"]) % 5
        # Le visuel identifie le cours, indépendamment de ses compétences.
        subject = row["title"].strip()
        compact = "".join(char for char in subject if char.isalnum())
        row["monogram"] = compact.upper() if len(compact) <= 4 else subject[:3]
        parsed = urlsplit(row["url"])
        row["external_url"] = row["url"] if parsed.scheme in ("http", "https") and parsed.netloc else ""
        row["source_domain"] = parsed.hostname or "Bibliothèque Web Semantic"
        return row

    def get(self, kind, identifier):
        # Snapshot assure la validation de l'identifiant et de la classe RDF.
        self.snapshot.get(kind, identifier)
        return self.by_id[identifier]

    def resolve(self, references):
        return [self.by_id[row["id"]] for row in references if row["id"] in self.by_id]

    def context(self, active="", **extra):
        return {"active": active, "counts": {key: len(rows) for key, rows in self.records.items()}, **extra}

    def ordered_courses(self, path):
        """Ordre suggéré : les prérequis internes précèdent leurs dépendants."""
        remaining = {row["id"]: row for row in self.resolve(path["courses"])}
        ordered = []
        while remaining:
            ready = [row for row in remaining.values() if not any(ref["id"] in remaining for ref in row["prerequisites"])]
            if not ready:
                # Résilience pour un import externe qui n'aurait pas été validé.
                ready = list(remaining.values())
            ready.sort(key=lambda row: (row["duration"], folded(row["title"])))
            for row in ready:
                ordered.append(row)
                remaining.pop(row["id"])
        return ordered
