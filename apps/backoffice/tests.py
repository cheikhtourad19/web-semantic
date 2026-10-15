from contextlib import nullcontext
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rdflib import Dataset, Graph, Namespace, RDF

from apps.semantic.catalogue import Catalogue, infer_catalogue, managed_file_key
from apps.semantic.validation import graph_uri
from .forms import EntityForm

EDU = Namespace("https://example.org/education#")


class MemoryStore:
    """Exécute réellement le SPARQL sur un dataset RDF isolé des données locales."""
    def __init__(self):
        self.dataset = Dataset()
        self.dataset.graph(graph_uri("catalogue")).parse(settings.BASE_DIR / "ontology/demo.ttl")

    def construct(self, sparql):
        return self.dataset.query(sparql).graph

    def update(self, sparql):
        self.dataset.update(sparql)


class CatalogueMutationTests(SimpleTestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.catalogue = Catalogue(self.store)
        self.lock = patch("apps.semantic.catalogue.catalogue_lock", side_effect=lambda: nullcontext())
        self.lock.start()
        self.addCleanup(self.lock.stop)

    def skill(self, title="Compétence de test"):
        return self.catalogue.save("competences", {"title": title, "description": "Description", "version": self.catalogue.snapshot().version})

    def course_data(self, **overrides):
        data = {"title": "Un nouveau cours", "description": "Un véritable cours de test.", "language": "fr", "duration": 90, "level": "Debutant", "skills": ["competence_python"], "required_skills": [], "prerequisites": [], "resources": [], "paths": ["parcours_semantique"], "version": self.catalogue.snapshot().version}
        return {**data, **overrides}

    def test_crud_uses_safe_rdf_literals_and_preserves_other_subjects(self):
        title = 'Python " ; DROP ALL ; #'
        identifier = self.skill(title)
        snapshot = self.catalogue.snapshot()
        self.assertEqual(snapshot.get("competences", identifier)["title"], title)
        self.assertEqual(len(snapshot.all("cours")), 8)
        self.catalogue.save("competences", {"title": "Nom modifié", "description": "", "version": snapshot.version}, identifier)
        self.catalogue.delete("competences", identifier, self.catalogue.snapshot().version)
        self.assertEqual(len(self.catalogue.snapshot().all("competences")), 9)

    def test_derived_relations_are_available_immediately_after_save(self):
        skill = self.skill()
        course = self.catalogue.save("cours", self.course_data(skills=[skill]))
        graph = self.store.dataset.graph(graph_uri("inferences"))
        self.assertIn((EDU.parcours_semantique, EDU.developpeCompetence, EDU[skill]), graph)
        self.assertIn((EDU[skill], EDU.estEnseigneePar, EDU[course]), graph)

    def test_stale_form_cannot_overwrite_new_data(self):
        version = self.catalogue.snapshot().version
        self.skill()
        with self.assertRaisesMessage(ValidationError, "Le catalogue a été modifié"):
            self.catalogue.save("competences", {"title": "Ancien formulaire", "version": version})
        self.assertEqual(len(self.catalogue.snapshot().all("competences")), 10)

    def test_deleting_a_used_skill_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.catalogue.delete("competences", "competence_python", self.catalogue.snapshot().version)
        self.assertEqual(len(self.catalogue.snapshot().all("competences")), 9)

    def test_deleting_a_prerequisite_course_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.catalogue.delete("cours", "cours_python", self.catalogue.snapshot().version)

    def test_a_course_cannot_leave_a_path_empty(self):
        course = self.catalogue.save("cours", self.course_data(paths=[]))
        self.catalogue.save("parcours", {"title": "Un seul cours", "description": "Un objectif précis.", "courses": [course], "version": self.catalogue.snapshot().version})
        with self.assertRaisesMessage(ValidationError, "doit conserver au moins un cours"):
            self.catalogue.delete("cours", course, self.catalogue.snapshot().version)
        self.assertEqual(len(self.catalogue.snapshot().all("cours")), 9)

    def test_edit_cannot_create_a_long_prerequisite_cycle(self):
        before = self.catalogue.snapshot().version
        with self.assertRaisesMessage(ValidationError, "boucle"):
            self.catalogue.save("cours", self.course_data(prerequisites=["cours_integration"]), "cours_algo")
        self.assertEqual(self.catalogue.snapshot().version, before)

    def test_pdf_upload_association_and_deletion(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            snapshot = self.catalogue.snapshot()
            data = {"title": "Support PDF", "description": "", "language": "fr", "resource_type": "DocumentPDF", "source": "file", "url": "", "courses": ["cours_python"], "file": SimpleUploadedFile("support.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"), "version": snapshot.version}
            identifier = self.catalogue.save("ressources", data)
            record = self.catalogue.snapshot().get("ressources", identifier)
            key = managed_file_key(record["url"])
            self.assertTrue(default_storage.exists(key))
            self.assertIn(identifier, [row["id"] for row in self.catalogue.snapshot().get("cours", "cours_python")["resources"]])
            self.assertIn((EDU[identifier], RDF.type, EDU.Ressource), self.store.dataset.graph(graph_uri("inferences")))
            self.catalogue.delete("ressources", identifier, self.catalogue.snapshot().version)
            self.assertFalse(default_storage.exists(key))
            self.assertNotIn(identifier, [row["id"] for row in self.catalogue.snapshot().get("cours", "cours_python")["resources"]])

    def test_invalid_pdf_is_rejected_by_form(self):
        form = EntityForm({"title": "Faux PDF", "description": "", "language": "fr", "resource_type": "DocumentPDF", "source": "file", "version": self.catalogue.snapshot().version}, {"file": SimpleUploadedFile("file.pdf", b"not a PDF")}, snapshot=self.catalogue.snapshot(), kind="ressources")
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_resource_form_keeps_its_existing_course_associations(self):
        snapshot = self.catalogue.snapshot()
        record = snapshot.get("ressources", "ressource_python")
        form = EntityForm(snapshot=snapshot, kind="ressources", record=record)
        self.assertEqual(form["courses"].value(), ["cours_python"])

    def test_pdf_edit_retains_file_and_associations_without_reuploading(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            data = {"title": "PDF original", "language": "fr", "resource_type": "DocumentPDF", "source": "file", "courses": ["cours_python"], "file": SimpleUploadedFile("test.pdf", b"%PDF-1.4\n%%EOF"), "version": self.catalogue.snapshot().version}
            identifier = self.catalogue.save("ressources", data)
            snapshot = self.catalogue.snapshot()
            record = snapshot.get("ressources", identifier)
            edited = {"title": "PDF modifié", "language": "fr", "resource_type": "DocumentPDF", "source": "file", "courses": ["cours_python"], "url": record["url"], "version": snapshot.version}
            form = EntityForm(edited, snapshot=snapshot, kind="ressources", record=record)
            self.assertTrue(form.is_valid(), form.errors)
            self.catalogue.save("ressources", form.cleaned_data, identifier)
            updated = self.catalogue.snapshot().get("ressources", identifier)
            self.assertEqual(updated["url"], record["url"])
            self.assertEqual(updated["used_by"], record["used_by"])
            self.assertTrue(default_storage.exists(managed_file_key(updated["url"])))

    def test_schema_inferences_match_previously_validated_examples(self):
        ontology = Graph().parse(settings.BASE_DIR / "ontology/education.ttl")
        inferences = infer_catalogue(ontology, self.catalogue.snapshot().graph)
        self.assertEqual(len(inferences), 57)
        self.assertIn((EDU.parcours_semantique, EDU.developpeCompetence, EDU.competence_rdf), inferences)


class BackofficeAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user("manager", password="test-password-strong", is_staff=True)
        cls.member = get_user_model().objects.create_user("member", password="test-password-strong")

    def setUp(self):
        self.catalogue = Catalogue(MemoryStore())
        self.repo_patch = patch("apps.backoffice.views.Catalogue", return_value=self.catalogue)
        self.repo_patch.start()
        self.addCleanup(self.repo_patch.stop)

    def test_anonymous_visitors_are_redirected_to_login(self):
        for route in ["/backoffice/", "/backoffice/cours/", "/backoffice/competences/nouveau/"]:
            with self.subTest(route=route):
                self.assertRedirects(self.client.get(route), f"/backoffice/connexion/?next={route}")

    def test_regular_user_cannot_access_management(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get("/backoffice/").status_code, 403)

    def test_login_form_refuses_regular_accounts(self):
        response = self.client.post("/backoffice/connexion/", {"username": "member", "password": "test-password-strong"})
        self.assertContains(response, "accès à l&#x27;espace de gestion")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_staff_can_use_all_management_screens(self):
        self.client.force_login(self.staff)
        routes = ["/backoffice/"]
        for kind in ["cours", "competences", "ressources", "parcours"]:
            routes.extend([f"/backoffice/{kind}/", f"/backoffice/{kind}/nouveau/"])
        routes.extend(["/backoffice/cours/cours_python/", "/backoffice/cours/cours_python/modifier/", "/backoffice/cours/cours_python/supprimer/"])
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

    def test_empty_post_shows_errors_instead_of_saving(self):
        self.client.force_login(self.staff)
        response = self.client.post("/backoffice/competences/nouveau/", {})
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Ce champ est obligatoire", status_code=422)

    def test_unknown_content_returns_404(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/backoffice/inconnu/" ).status_code, 404)
        self.assertEqual(self.client.get("/backoffice/cours/inconnu/" ).status_code, 404)

    def test_delete_is_never_triggered_by_get(self):
        self.client.force_login(self.staff)
        response = self.client.get("/backoffice/competences/competence_python/supprimer/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.catalogue.snapshot().all("competences")), 9)

    def test_forms_require_csrf_tokens(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post("/backoffice/competences/nouveau/", {"title": "No CSRF"}).status_code, 403)
