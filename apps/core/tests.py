from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase

from apps.semantic.services import SemanticStoreError


class HealthTests(SimpleTestCase):
    @patch("apps.core.views.SemanticStore.query", return_value={"boolean": False})
    @patch("apps.core.views.connection")
    def test_empty_but_reachable_graph_is_healthy(self, database, query):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["services"], {"postgresql": "ok", "fuseki": "ok"})

    @patch("apps.core.views.SemanticStore.query", side_effect=SemanticStoreError("offline"))
    @patch("apps.core.views.connection")
    def test_fuseki_failure_is_reported_without_exposing_details(self, database, query):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["services"]["fuseki"], "unavailable")
        self.assertNotContains(response, "offline", status_code=503)

    @patch("apps.core.views.SemanticStore.query", return_value={"boolean": False})
    @patch("apps.core.views.connection")
    def test_postgres_failure_is_reported(self, database, query):
        database.cursor.side_effect = OperationalError("internal database details")
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["services"]["postgresql"], "unavailable")

