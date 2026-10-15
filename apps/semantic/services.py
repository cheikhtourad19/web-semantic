import httpx
from django.conf import settings
from rdflib import Graph


class SemanticStoreError(Exception):
    """Fuseki est indisponible ou a rejete l'operation."""


class SemanticStore:
    def __init__(self):
        self.base_url = settings.FUSEKI_DATASET_URL
        self.timeout = settings.FUSEKI_TIMEOUT_SECONDS

    def construct(self, sparql):
        try:
            response = httpx.post(
                f"{self.base_url}/query", data={"query": sparql},
                headers={"Accept": "text/turtle"}, timeout=self.timeout, trust_env=False,
            )
            response.raise_for_status()
            return Graph().parse(data=response.text, format="turtle")
        except (httpx.HTTPError, SyntaxError, ValueError) as exc:
            raise SemanticStoreError("Le catalogue est momentanément indisponible.") from exc

    def update(self, sparql):
        """Une requête Update regroupe les changements des faits et des inférences."""
        try:
            response = httpx.post(
                f"{self.base_url}/update", content=sparql,
                headers={"Content-Type": "application/sparql-update"},
                timeout=max(self.timeout, 15), trust_env=False,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SemanticStoreError("L'enregistrement n'a pas pu être confirmé. Actualisez avant de réessayer.") from exc

    def query(self, sparql):
        try:
            response = httpx.post(
                f"{self.base_url}/query",
                data={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
                timeout=self.timeout,
                trust_env=False,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SemanticStoreError("Impossible d'interroger Fuseki.") from exc

    def replace_graph(self, graph_uri, graph: Graph):
        """Remplace uniquement le graphe nomme cible, pas les autres donnees."""
        try:
            response = httpx.put(
                f"{self.base_url}/data",
                params={"graph": graph_uri},
                content=graph.serialize(format="turtle"),
                headers={"Content-Type": "text/turtle; charset=utf-8"},
                timeout=self.timeout,
                trust_env=False,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SemanticStoreError("Impossible d'enregistrer le graphe dans Fuseki.") from exc

    def get_graph(self, graph_uri):
        try:
            response = httpx.get(
                f"{self.base_url}/data", params={"graph": graph_uri},
                headers={"Accept": "text/turtle"}, timeout=self.timeout, trust_env=False,
            )
            if response.status_code == 404:
                return Graph()
            response.raise_for_status()
            return Graph().parse(data=response.text, format="turtle")
        except (httpx.HTTPError, SyntaxError, ValueError) as exc:
            raise SemanticStoreError("Impossible de lire le graphe dans Fuseki.") from exc

    def add_graph(self, graph_uri, graph: Graph):
        """Ajoute des triplets sans remplacer les autres données du graphe."""
        try:
            response = httpx.post(
                f"{self.base_url}/data", params={"graph": graph_uri},
                content=graph.serialize(format="turtle"),
                headers={"Content-Type": "text/turtle; charset=utf-8"},
                timeout=self.timeout, trust_env=False,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SemanticStoreError("Impossible d'ajouter les données dans Fuseki.") from exc

    def delete_graph(self, graph_uri):
        try:
            response = httpx.delete(
                f"{self.base_url}/data", params={"graph": graph_uri},
                timeout=self.timeout, trust_env=False,
            )
            if response.status_code != 404:
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SemanticStoreError("Impossible d'invalider le graphe d'inférences.") from exc

