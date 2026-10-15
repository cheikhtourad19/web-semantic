"""Contrats ciblés de la recherche IA. Aucun appel à une API réelle."""
import json
from unittest.mock import patch

import httpx
from django.conf import settings
from django.test import SimpleTestCase, override_settings
from rdflib import Dataset, Graph, URIRef

from apps.semantic.catalogue import Snapshot
from apps.semantic.validation import graph_uri
from .ai_search import AISearchError, SearchPlan, translate_question, validate_plan
from .catalogue import PublicCatalogue


@override_settings(GEMINI_API_KEY="test-key-not-real", GEMINI_MODEL="gemini-3.8-flash")
class AISearchContractTests(SimpleTestCase):
    def setUp(self):
        graph = Graph().parse(settings.BASE_DIR / "ontology/demo.ttl")
        self.snapshot_patch = patch("apps.core.catalogue.Catalogue.snapshot", return_value=Snapshot(graph))
        self.snapshot_patch.start()
        self.addCleanup(self.snapshot_patch.stop)
        self.catalogue = PublicCatalogue()
        self.query = f"""PREFIX edu: <{settings.SEMANTIC_NAMESPACE}>
SELECT DISTINCT ?entity ?titre FROM <{graph_uri('catalogue')}> WHERE {{
 ?entity a edu:Cours ; edu:titre ?titre ; edu:aPourNiveau edu:Debutant ; edu:dureeMinutes ?minutes .
 FILTER(?minutes < 120)
}} ORDER BY ?titre LIMIT 50"""

    @override_settings(GEMINI_API_KEY="")
    @patch("apps.core.ai_search.httpx.post")
    def test_no_key_never_contacts_the_provider(self, post):
        with self.assertRaises(AISearchError):
            translate_question("Des cours pour débuter", self.catalogue)
        post.assert_not_called()

    @patch("apps.core.ai_search.httpx.post")
    def test_provider_contract_and_quota_error(self, post):
        payload = {"status": "ready", "explanation": "Les cours débutants de moins de deux heures.", "sparql": self.query}
        post.return_value = httpx.Response(200, request=httpx.Request("POST", "https://example.org"), json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}]})
        plan = translate_question("Des cours débutants courts", self.catalogue)
        self.assertEqual(plan.sparql, self.query)
        args = post.call_args.kwargs
        self.assertEqual(args["headers"]["x-goog-api-key"], "test-key-not-real")
        self.assertNotIn("test-key-not-real", json.dumps(args["json"]))
        self.assertIn("education/graphs/catalogue", args["json"]["systemInstruction"]["parts"][0]["text"])
        self.assertIn("public_catalogue_labels", args["json"]["contents"][0]["parts"][0]["text"])
        post.return_value = httpx.Response(429)
        with self.assertRaises(AISearchError) as failure:
            translate_question("Des cours", self.catalogue)
        self.assertEqual(failure.exception.status, 429)

    def test_ai_output_must_be_a_safe_entity_selection(self):
        for query in ("DROP ALL", "SELECT ?titre WHERE { ?s ?p ?titre }", "SELECT ?entity WHERE { SERVICE <https://example.org> { ?entity ?p ?o } }"):
            with self.subTest(query=query), self.assertRaises(AISearchError):
                validate_plan({"status": "ready", "explanation": "Une recherche", "sparql": query})
        plan = validate_plan({"status": "clarify", "explanation": "Quel sujet souhaitez-vous apprendre ?", "sparql": ""})
        self.assertEqual(plan.status, "clarify")

    @patch("apps.core.views.translate_question")
    @patch("apps.core.views.execute_query")
    def test_question_results_are_cards_from_the_rdf_catalogue(self, execute, translate):
        dataset = Dataset()
        graph = dataset.graph(URIRef(graph_uri("catalogue")))
        graph += self.catalogue.snapshot.graph
        result = json.loads(dataset.query(self.query).serialize(format="json"))
        result.update({"elapsed": 1, "query_type": "SELECT", "truncated": False})
        execute.return_value = result
        translate.return_value = SearchPlan("ready", "Les cours débutants de moins de deux heures.", self.query)
        response = self.client.post("/recherche/", {"mode": "ai", "question": "Des cours débutants de moins de deux heures"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["match_count"], 2)
        self.assertEqual([row["title"] for row in response.context["groups"][0]["rows"]], ["Comprendre HTTP", "Fondamentaux de l'algorithmique"])
        self.assertContains(response, 'class="course-card')
        self.assertContains(response, "Voir la requête SPARQL générée")
