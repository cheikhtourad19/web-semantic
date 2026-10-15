"""Catalogue RDF : lecture SPARQL, validation et mutations atomiques dans Fuseki."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import logging
import re
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import connection, transaction
from django.http import Http404
from django.utils import timezone
from owlrl import DeductiveClosure, OWLRL_Semantics
from rdflib import Graph, Literal, Namespace, RDF, URIRef, XSD

from .services import SemanticStore
from .validation import CatalogueValidationError, fingerprint, graph_uri, validate_catalogue

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Kind:
    key: str
    singular: str
    plural: str
    owl_class: str
    icon: str
    description: str

    @property
    def with_article(self):
        return ("la " if self.key in ("competences", "ressources") else "le ") + self.singular

    @property
    def indefinite(self):
        return ("une " if self.key in ("competences", "ressources") else "un ") + self.singular


KINDS = {
    "cours": Kind("cours", "cours", "Cours", "Cours", "book", "Les savoirs prennent forme ici."),
    "competences": Kind("competences", "compétence", "Compétences", "Competence", "spark", "Le vocabulaire de votre catalogue."),
    "ressources": Kind("ressources", "ressource", "Ressources", "Ressource", "file", "Des supports pour aller plus loin."),
    "parcours": Kind("parcours", "parcours", "Parcours", "ParcoursApprentissage", "route", "Reliez les cours autour d'un objectif."),
}
RESOURCE_TYPES = {"DocumentPDF": "PDF", "PageWeb": "Page web", "Video": "Vidéo", "Exercice": "Exercice"}
LEVELS = {"Debutant": "Débutant", "Intermediaire": "Intermédiaire", "Avance": "Avancé"}


def get_kind(key):
    if key not in KINDS:
        raise Http404
    return KINDS[key]


def managed_file_key(url):
    parsed = urlsplit(url)
    prefix = settings.MEDIA_URL
    if parsed.scheme or parsed.netloc or not parsed.path.startswith(prefix):
        return None
    key = unquote(parsed.path[len(prefix):])
    return key if re.fullmatch(r"resources/[A-Za-z0-9_-]+\.pdf", key) else None


@contextmanager
def catalogue_lock():
    # Le verrou PostgreSQL sérialise les écritures des workers Django.
    # Les entités métier restent exclusivement dans Fuseki.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [728413091])
        yield


def infer_catalogue(ontology, catalogue):
    base = ontology + catalogue
    closure = Graph()
    closure += base
    DeductiveClosure(OWLRL_Semantics, improved_datatypes=False).expand(closure)
    namespace = settings.SEMANTIC_NAMESPACE
    result = Graph()
    for subject, predicate, obj in closure - base:
        if isinstance(subject, URIRef) and str(subject).startswith(namespace):
            if str(predicate).startswith(namespace) or (predicate == RDF.type and str(obj).startswith(namespace)):
                result.add((subject, predicate, obj))
    return result


class Snapshot:
    def __init__(self, graph):
        self.graph = graph
        self.edu = Namespace(settings.SEMANTIC_NAMESPACE)
        self.version = fingerprint(graph)
        self._records = {}

    def uri(self, identifier):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
            raise Http404
        return self.edu[identifier]

    def identifier(self, uri):
        value = str(uri)
        if not value.startswith(str(self.edu)):
            raise Http404
        return value[len(str(self.edu)):]

    def subjects(self, kind):
        classes = [self.edu[KINDS[kind].owl_class]]
        if kind == "ressources":
            classes += [self.edu[name] for name in RESOURCE_TYPES]
        return {subject for cls in classes for subject in self.graph.subjects(RDF.type, cls)}

    def all(self, kind):
        if kind not in self._records:
            self._records[kind] = sorted(
                [self.record(kind, subject) for subject in self.subjects(kind)],
                key=lambda row: row["title"].casefold(),
            )
        return self._records[kind]

    def record(self, kind, subject):
        graph, edu = self.graph, self.edu
        def value(prop, default=""):
            return str(graph.value(subject, edu[prop]) or default)
        level = self.identifier(graph.value(subject, edu.aPourNiveau)) if graph.value(subject, edu.aPourNiveau) else ""
        resource_type = next((key for key in RESOURCE_TYPES if (subject, RDF.type, edu[key]) in graph), "PageWeb")
        modified = value("modifieLe") or value("creeLe")
        try:
            modified_date = datetime.fromisoformat(modified) if modified else None
        except ValueError:
            modified_date = None
        result = {
            "id": self.identifier(subject), "uri": str(subject), "kind": kind,
            "title": value("libelle" if kind == "competences" else "titre"),
            "description": value("description"), "language": value("langue", "fr"),
            "duration": int(value("dureeMinutes", "0")), "level": level,
            "level_label": LEVELS.get(level, ""), "resource_type": resource_type,
            "format_label": RESOURCE_TYPES[resource_type], "url": value("urlAcces"),
            "filename": value("nomFichier"), "size": int(value("tailleOctets", "0")),
            "modified": modified_date,
        }
        result["is_local_pdf"] = resource_type == "DocumentPDF" and bool(managed_file_key(result["url"]))
        result["skills"] = self.related(subject, edu.enseigne, "competences")
        result["required_skills"] = self.related(subject, edu.exigeCompetence, "competences")
        result["prerequisites"] = self.related(subject, edu.aPourPrerequisCours, "cours")
        result["resources"] = self.related(subject, edu.aPourRessource, "ressources")
        result["courses"] = self.related(subject, edu.contientCours, "cours") if kind == "parcours" else []
        result["paths"] = self.incoming(subject, edu.contientCours, "parcours")
        result["used_by"] = self.incoming(subject, edu.aPourRessource if kind == "ressources" else edu.enseigne, "cours")
        result["required_by"] = self.incoming(subject, edu.exigeCompetence, "cours")
        result["prerequisite_of"] = self.incoming(subject, edu.aPourPrerequisCours, "cours")
        if kind == "parcours":
            course_uris = list(graph.objects(subject, edu.contientCours))
            result["duration"] = sum(int(graph.value(course, edu.dureeMinutes) or 0) for course in course_uris)
            skills = {skill for course in course_uris for skill in graph.objects(course, edu.enseigne)}
            result["skills"] = sorted([self.reference("competences", skill) for skill in skills], key=lambda x: x["title"])
        return result

    def reference(self, kind, subject):
        prop = self.edu.libelle if kind == "competences" else self.edu.titre
        return {"id": self.identifier(subject), "kind": kind, "title": str(self.graph.value(subject, prop) or "Sans titre")}

    def related(self, subject, prop, kind):
        return sorted([self.reference(kind, obj) for obj in self.graph.objects(subject, prop)], key=lambda x: x["title"])

    def incoming(self, subject, prop, kind):
        return sorted([self.reference(kind, obj) for obj in self.graph.subjects(prop, subject)], key=lambda x: x["title"])

    def get(self, kind, identifier):
        subject = self.uri(identifier)
        if subject not in self.subjects(kind):
            raise Http404
        return self.record(kind, subject)


class Catalogue:
    def __init__(self, store=None):
        self.store = store or SemanticStore()

    def snapshot(self):
        uri = URIRef(graph_uri("catalogue")).n3()
        return Snapshot(self.store.construct(f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH {uri} {{ ?s ?p ?o }} }}"))

    def _persist(self, before, after):
        try:
            ontology = validate_catalogue(after)
        except CatalogueValidationError as exc:
            logger.info("Validation SHACL refusée : %s", exc)
            raise ValidationError("Ce changement rend certaines relations invalides. Vérifiez les compétences, les prérequis et le contenu des parcours.") from exc
        inferred = infer_catalogue(ontology, after)
        cat = URIRef(graph_uri("catalogue")).n3()
        inf = URIRef(graph_uri("inferences")).n3()
        removed, added = before - after, after - before
        operations = []
        if len(removed):
            operations.append(f"DELETE DATA {{ GRAPH {cat} {{ {removed.serialize(format='nt')} }} }}")
        if len(added):
            operations.append(f"INSERT DATA {{ GRAPH {cat} {{ {added.serialize(format='nt')} }} }}")
        operations.append(f"DROP SILENT GRAPH {inf}")
        if len(inferred):
            operations.append(f"INSERT DATA {{ GRAPH {inf} {{ {inferred.serialize(format='nt')} }} }}")
        self.store.update(";\n".join(operations))

    def save(self, kind, data, identifier=None):
        new_file = None
        writing = False
        old_file = None
        try:
            with catalogue_lock():
                snapshot = self.snapshot()
                if data.get("version") != snapshot.version:
                    raise ValidationError("Le catalogue a été modifié depuis l'ouverture du formulaire. Rechargez cette page avant d'enregistrer.")
                existing = snapshot.get(kind, identifier) if identifier else None
                identifier = identifier or f"{KINDS[kind].owl_class.lower()}_{uuid4().hex}"
                subject, edu = snapshot.uri(identifier), snapshot.edu
                graph = Graph()
                graph += snapshot.graph
                created = graph.value(subject, edu.creeLe)
                graph.remove((subject, None, None))
                graph.add((subject, RDF.type, edu[data.get("resource_type", KINDS[kind].owl_class)]))
                graph.add((subject, edu.creeLe, created or Literal(timezone.now(), datatype=XSD.dateTime)))
                graph.add((subject, edu.modifieLe, Literal(timezone.now(), datatype=XSD.dateTime)))
                graph.add((subject, edu.libelle if kind == "competences" else edu.titre, Literal(data["title"])))
                if data.get("description"):
                    graph.add((subject, edu.description, Literal(data["description"])))
                if kind in ("cours", "ressources"):
                    graph.add((subject, edu.langue, Literal(data["language"])))
                if kind == "cours":
                    graph.add((subject, edu.dureeMinutes, Literal(data["duration"], datatype=XSD.nonNegativeInteger)))
                    graph.add((subject, edu.aPourNiveau, edu[data["level"]]))
                    for field, prop in [("skills", "enseigne"), ("required_skills", "exigeCompetence"), ("prerequisites", "aPourPrerequisCours"), ("resources", "aPourRessource")]:
                        for target in data.get(field, []):
                            graph.add((subject, edu[prop], snapshot.uri(target)))
                    graph.remove((None, edu.contientCours, subject))
                    for target in data.get("paths", []):
                        graph.add((snapshot.uri(target), edu.contientCours, subject))
                elif kind == "parcours":
                    for target in data["courses"]:
                        graph.add((subject, edu.contientCours, snapshot.uri(target)))
                elif kind == "ressources":
                    old_file = managed_file_key(existing["url"]) if existing else None
                    upload = data.get("file")
                    url = data.get("url", "")
                    if data["source"] == "file":
                        if upload:
                            new_file = default_storage.save(f"resources/{uuid4().hex}.pdf", upload)
                            url = default_storage.url(new_file)
                            graph.add((subject, edu.nomFichier, Literal(upload.name)))
                            graph.add((subject, edu.tailleOctets, Literal(upload.size, datatype=XSD.nonNegativeInteger)))
                        elif existing:
                            url = existing["url"]
                            if existing["filename"]:
                                graph.add((subject, edu.nomFichier, Literal(existing["filename"])))
                            if existing["size"]:
                                graph.add((subject, edu.tailleOctets, Literal(existing["size"], datatype=XSD.nonNegativeInteger)))
                    graph.add((subject, edu.urlAcces, Literal(url, datatype=XSD.anyURI)))
                    graph.remove((None, edu.aPourRessource, subject))
                    for target in data.get("courses", []):
                        graph.add((snapshot.uri(target), edu.aPourRessource, subject))
                    if old_file and url == existing["url"]:
                        old_file = None
                self._check_business_rules(graph, edu)
                # En cas de réponse réseau incertaine, conserver le nouveau fichier :
                # Fuseki peut avoir reçu l'écriture. Cela évite une référence cassée.
                writing = True
                self._persist(snapshot.graph, graph)
                self._cleanup_file(old_file, graph, edu)
                return identifier
        except Exception as exc:
            if new_file and (not writing or isinstance(exc, ValidationError)):
                default_storage.delete(new_file)
            raise

    @staticmethod
    def _check_business_rules(graph, edu):
        for path in graph.subjects(RDF.type, edu.ParcoursApprentissage):
            if not any(graph.objects(path, edu.contientCours)):
                title = graph.value(path, edu.titre)
                raise ValidationError(f"Le parcours « {title} » doit conserver au moins un cours.")
        for course in graph.subjects(RDF.type, edu.Cours):
            pending = list(graph.objects(course, edu.aPourPrerequisCours))
            seen = set()
            while pending:
                current = pending.pop()
                if current == course:
                    raise ValidationError("Ces prérequis créent une boucle entre les cours. Choisissez un autre enchaînement.")
                if current not in seen:
                    seen.add(current)
                    pending.extend(graph.objects(current, edu.aPourPrerequisCours))

    def delete(self, kind, identifier, version):
        with catalogue_lock():
            snapshot = self.snapshot()
            if version != snapshot.version:
                raise ValidationError("Le catalogue a changé. Rechargez la page avant de supprimer cet élément.")
            record = snapshot.get(kind, identifier)
            blockers = deletion_blockers(record)
            if blockers:
                raise ValidationError("Cet élément est encore utilisé. Modifiez d'abord les éléments qui en dépendent.")
            subject, edu = snapshot.uri(identifier), snapshot.edu
            graph = Graph()
            graph += snapshot.graph
            graph.remove((subject, None, None))
            graph.remove((None, None, subject))
            self._check_business_rules(graph, edu)
            self._persist(snapshot.graph, graph)
            if kind == "ressources":
                self._cleanup_file(managed_file_key(record["url"]), graph, edu)

    @staticmethod
    def _cleanup_file(key, graph, edu):
        if not key:
            return
        if any(managed_file_key(str(url)) == key for url in graph.objects(None, edu.urlAcces)):
            return
        try:
            default_storage.delete(key)
        except OSError:
            logger.exception("Nettoyage différé du fichier média %s", key)


def deletion_blockers(record):
    if record["kind"] == "competences":
        return record["used_by"] + record["required_by"]
    if record["kind"] == "cours":
        return record["prerequisite_of"]
    return []
