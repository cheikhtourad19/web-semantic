"""Atelier SPARQL public : SELECT/ASK bornés et aucun accès réseau fédéré."""
import json
import re
from time import perf_counter

import httpx
from django import forms
from django.conf import settings
from pyparsing import ParseResults
from rdflib import URIRef
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.parserutils import CompValue

from apps.semantic.services import SemanticStoreError
from apps.semantic.validation import graph_uri

MAX_ROWS = 200
MAX_BYTES = 2 * 1024 * 1024


class QueryError(ValueError):
    pass


class QueryForm(forms.Form):
    query = forms.CharField(
        label="Votre requête SPARQL", max_length=12000, strip=True,
        widget=forms.Textarea(attrs={"spellcheck": "false", "autocapitalize": "off", "autocomplete": "off", "rows": 17, "aria-describedby": "query-help"}),
        error_messages={"required": "Écrivez une requête ou choisissez un exemple.", "max_length": "La requête est limitée à 12 000 caractères."},
    )


def examples():
    prefix = f"PREFIX edu: <{settings.SEMANTIC_NAMESPACE}>\n"
    cat, inf = graph_uri("catalogue"), graph_uri("inferences")
    return [
        {"id": "cours", "title": "Explorer les cours", "description": "Titres, niveaux et durées du catalogue.", "icon": "book", "query": prefix + f"""SELECT ?cours ?titre ?niveau ?minutes
WHERE {{
  GRAPH <{cat}> {{
    ?cours a edu:Cours ;
           edu:titre ?titre ;
           edu:aPourNiveau ?niveau ;
           edu:dureeMinutes ?minutes .
  }}
}}
ORDER BY ?titre"""},
        {"id": "debutants", "title": "Commencer en douceur", "description": "Les cours accessibles aux débutants.", "icon": "spark", "query": prefix + f"""SELECT ?cours ?titre ?minutes
WHERE {{
  GRAPH <{cat}> {{
    ?cours a edu:Cours ;
           edu:aPourNiveau edu:Debutant ;
           edu:titre ?titre ;
           edu:dureeMinutes ?minutes .
  }}
}}
ORDER BY ?minutes"""},
        {"id": "prerequis", "title": "Remonter les prérequis", "description": "Suivre les dépendances, même indirectes, avec +.", "icon": "route", "query": prefix + f"""SELECT DISTINCT ?titre ?prerequis
WHERE {{
  GRAPH <{cat}> {{
    ?cours edu:titre ?titre ;
           edu:aPourPrerequisCours+ ?avant .
    ?avant edu:titre ?prerequis .
  }}
}}
ORDER BY ?titre ?prerequis"""},
        {"id": "competences", "title": "Relier cours et compétences", "description": "Retrouver ce que chaque cours enseigne.", "icon": "link", "query": prefix + f"""SELECT ?titre ?competence
WHERE {{
  GRAPH <{cat}> {{
    ?cours a edu:Cours ;
           edu:titre ?titre ;
           edu:enseigne ?savoir .
    ?savoir edu:libelle ?competence .
  }}
}}
ORDER BY ?titre ?competence"""},
        {"id": "inferences", "title": "Voir les déductions", "description": "Les compétences des parcours, déduites automatiquement.", "icon": "spark", "query": prefix + f"""SELECT ?parcours ?competence
WHERE {{
  GRAPH <{inf}> {{
    ?chemin edu:developpeCompetence ?savoir .
  }}
  GRAPH <{cat}> {{
    ?chemin edu:titre ?parcours .
    ?savoir edu:libelle ?competence .
  }}
}}
ORDER BY ?parcours ?competence"""},
        {"id": "verification", "title": "Poser une question oui/non", "description": "ASK : existe-t-il un cours pour débuter ?", "icon": "check", "query": prefix + f"""ASK {{
  GRAPH <{cat}> {{
    ?cours a edu:Cours ;
           edu:aPourNiveau edu:Debutant .
  }}
}}"""},
    ]


def walk(value):
    if isinstance(value, CompValue):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, (list, tuple, ParseResults)):
        for child in value:
            yield from walk(child)


# Ignore les commentaires, les littéraux et les IRI lors de la recherche du
# mot-clé SELECT : un préfixe ou un commentaire peut lui-même contenir ce mot.
TOKENS = re.compile(r'#[^\r\n]*|<[^<>\s]*>|"""[\s\S]*?"""|\x27\x27\x27[\s\S]*?\x27\x27\x27|"(?:[^"\\]|\\.)*"|\x27(?:[^\x27\\]|\\.)*\x27|[?$][\w]+|[A-Za-z_][A-Za-z0-9_.:-]*')


def prepare_query(query):
    if len(query) > 12000:
        raise QueryError("La requête est limitée à 12 000 caractères.")
    try:
        parsed = parseQuery(query)
        query_type = parsed[1].name
        if query_type not in ("SelectQuery", "AskQuery"):
            raise QueryError("Cet atelier accepte uniquement SELECT et ASK, en lecture seule.")
        algebra = translateQuery(parsed).algebra
    except Exception as exc:
        if isinstance(exc, QueryError):
            raise
        line = getattr(exc, "lineno", None)
        column = getattr(exc, "col", None)
        position = f" (ligne {line}, colonne {column})" if line else ""
        raise QueryError(f"La syntaxe SPARQL est invalide{position}. Vérifiez les préfixes, les accolades et les points.") from exc
    allowed = {URIRef(graph_uri(name)) for name in ("catalogue", "ontology", "inferences")}
    for node in walk(algebra):
        if node.name == "ServiceGraphPattern":
            raise QueryError("SERVICE est désactivé : l’atelier interroge uniquement le catalogue local.")
        if node.name == "DatasetClause" and any(node[key] not in allowed for key in ("default", "named") if key in node):
            raise QueryError("FROM doit désigner l’un des trois graphes locaux indiqués dans l’aide.")
        if node.name == "Function" and not str(node.get("iri", "")).startswith("http://www.w3.org/2001/XMLSchema#"):
            raise QueryError("Les fonctions d’extension externes ne sont pas disponibles dans cet atelier.")
    if query_type == "SelectQuery":
        tokens = [match for match in TOKENS.finditer(query) if not match.group().startswith("#")]
        start = next(match.start() for match in tokens if match.group().upper() == "SELECT")
        # FROM appartient à la requête extérieure : SPARQL ne l'autorise pas
        # dans un sous-SELECT. Les URI ont déjà été contrôlées ci-dessus.
        clauses = []
        spans = []
        for index, token in enumerate(tokens):
            if token.start() >= start and token.group().upper() == "FROM":
                end_index = index + (2 if tokens[index + 1].group().upper() == "NAMED" else 1)
                end = tokens[end_index].end()
                clauses.append(query[token.start():end])
                spans.append((token.start(), end))
        body = query[start:]
        for begin, end in reversed(spans):
            body = body[:begin - start] + body[end - start:]
        # Le sous-SELECT conserve GROUP BY, ORDER BY et une éventuelle limite
        # utilisateur ; la limite extérieure borne aussi les requêtes sans LIMIT.
        query = f"{query[:start]}SELECT * {' '.join(clauses)} WHERE {{\n{{\n{body}\n}}\n}} LIMIT {MAX_ROWS + 1}"
    return query, query_type


def execute_query(query):
    prepared, query_type = prepare_query(query)
    started = perf_counter()
    try:
        with httpx.stream(
            "POST", f"{settings.FUSEKI_DATASET_URL}/query",
            params={"timeout": "5000"}, data={"query": prepared},
            headers={"Accept": "application/sparql-results+json"}, timeout=8, trust_env=False,
        ) as response:
            if response.status_code == 400:
                raise QueryError("Fuseki a refusé cette requête. Vérifiez les expressions et les types utilisés.")
            if response.status_code in (408, 503):
                raise QueryError("La requête a pris trop de temps. Simplifiez les motifs ou ajoutez des filtres.")
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    raise QueryError("Le résultat est trop volumineux. Sélectionnez moins de colonnes ou ajoutez des filtres.")
        result = json.loads(content)
    except httpx.TimeoutException as exc:
        raise QueryError("Le délai d’exécution est dépassé. Essayez une requête plus ciblée.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, QueryError):
            raise
        raise SemanticStoreError("L’atelier ne peut pas joindre Fuseki pour le moment.") from exc
    result["elapsed"] = round((perf_counter() - started) * 1000)
    result["query_type"] = "SELECT" if query_type == "SelectQuery" else "ASK"
    if query_type == "SelectQuery":
        bindings = result.get("results", {}).get("bindings", [])
        result["truncated"] = len(bindings) > MAX_ROWS
        result["results"]["bindings"] = bindings[:MAX_ROWS]
    return result
