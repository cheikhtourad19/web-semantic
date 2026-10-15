from django.conf import settings
from pyshacl import validate
from rdflib import Graph
from rdflib.compare import to_isomorphic


class CatalogueValidationError(ValueError):
    pass


def graph_uri(name):
    return f"{settings.SEMANTIC_NAMESPACE.rstrip('#/')}/graphs/{name}"


def fingerprint(graph):
    """Empreinte indépendante des identifiants temporaires des nœuds anonymes."""
    return str(to_isomorphic(graph).graph_digest())


def validate_catalogue(catalogue):
    ontology = Graph().parse(settings.BASE_DIR / "ontology/education.ttl")
    shapes = Graph().parse(settings.BASE_DIR / "ontology/shapes.ttl")
    conforms, report, report_text = validate(
        catalogue, shacl_graph=shapes, ont_graph=ontology,
        inference="none", inplace=False, advanced=True,
    )
    if not conforms:
        raise CatalogueValidationError(report_text)
    return ontology
