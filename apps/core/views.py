from django.conf import settings
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import DatabaseError, connection
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods

from apps.semantic.catalogue import KINDS, LEVELS, RESOURCE_TYPES, managed_file_key
from apps.semantic.services import SemanticStore, SemanticStoreError
from apps.semantic.validation import graph_uri
from .ai_search import AISearchError, QuestionForm, SUGGESTIONS, check_rate_limit, configured, result_groups, translate_question
from .catalogue import PublicCatalogue, folded, public_view
from .sparql import MAX_ROWS, QueryError, QueryForm, examples, execute_query


@require_GET
@public_view
def home(request):
    catalogue = PublicCatalogue()
    courses = catalogue.records["cours"]
    starters = sorted(courses, key=lambda row: (bool(row["prerequisites"]), row["level"] != "Debutant", row["duration"]))[:3]
    featured_paths = sorted(catalogue.records["parcours"], key=lambda row: len(row["courses"]))[:3]
    skills = sorted(catalogue.records["competences"], key=lambda row: -len(row["used_by"]))[:9]
    graph_course = next((row for row in courses if row["skills"] and row["paths"]), None)
    graph_path = catalogue.resolve(graph_course["paths"])[0] if graph_course else None
    graph_skills = catalogue.resolve(graph_course["skills"])[:2] if graph_course else []
    return render(request, "core/home.html", catalogue.context("home", courses=starters, paths=featured_paths, skills=skills, graph_course=graph_course, graph_path=graph_path, graph_skills=graph_skills))


@require_GET
@public_view
def catalogue_list(request, kind="cours"):
    if kind not in KINDS:
        raise Http404
    catalogue = PublicCatalogue()
    all_rows = catalogue.records[kind]
    rows = all_rows
    q = request.GET.get("q", "").strip()[:200]
    level = request.GET.get("niveau", "") if kind == "cours" else ""
    skill = request.GET.get("competence", "") if kind in ("cours", "parcours") else ""
    resource_format = request.GET.get("format", "") if kind == "ressources" else ""
    language = request.GET.get("langue", "") if kind in ("cours", "ressources") else ""
    sort = request.GET.get("tri", "titre")
    if q:
        rows = [row for row in rows if folded(q) in folded(" ".join([row["title"], row["description"], *[ref["title"] for ref in row["skills"]]]))]
    if level in LEVELS:
        rows = [row for row in rows if row["level"] == level]
    else:
        level = ""
    if skill in catalogue.by_id and catalogue.by_id[skill]["kind"] == "competences":
        rows = [row for row in rows if any(ref["id"] == skill for ref in row["skills"])]
    else:
        skill = ""
    if resource_format in RESOURCE_TYPES:
        rows = [row for row in rows if row["resource_type"] == resource_format]
    else:
        resource_format = ""
    languages = sorted({row["language"] for row in all_rows}) if kind in ("cours", "ressources") else []
    if language in languages:
        rows = [row for row in rows if row["language"] == language]
    else:
        language = ""
    if sort == "duree" and kind in ("cours", "parcours"):
        rows = sorted(rows, key=lambda row: row["duration"])
    elif sort == "niveau" and kind == "cours":
        rows = sorted(rows, key=lambda row: list(LEVELS).index(row["level"]) if row["level"] in LEVELS else 9)
    else:
        sort = "titre"
    page = Paginator(rows, 9).get_page(request.GET.get("page"))
    parameters = request.GET.copy()
    parameters.pop("page", None)
    levels = [{"id": key, "label": label, "count": sum(row["level"] == key for row in all_rows)} for key, label in LEVELS.items()]
    formats = [{"id": key, "label": label, "count": sum(row["resource_type"] == key for row in all_rows)} for key, label in RESOURCE_TYPES.items()]
    language_options = [{"id": key, "label": next(row["language_label"] for row in all_rows if row["language"] == key)} for key in languages]
    return render(request, "core/catalogue.html", catalogue.context(kind, kind=kind, config=KINDS[kind], rows=page, total=len(all_rows), result_count=len(rows), q=q, level=level, skill=skill, resource_format=resource_format, language=language, sort=sort, levels=levels, formats=formats, languages=language_options, skills=catalogue.records["competences"], filtered=bool(q or level or skill or resource_format or language), pagination_query=urlencode(parameters)))


@require_GET
@public_view
def entity_detail(request, kind, identifier):
    if kind not in KINDS:
        raise Http404
    catalogue = PublicCatalogue()
    record = catalogue.get(kind, identifier)
    context = catalogue.context(kind, kind=kind, config=KINDS[kind], record=record)
    for key in ("skills", "required_skills", "prerequisites", "resources", "paths", "used_by", "required_by", "prerequisite_of"):
        context[key] = catalogue.resolve(record[key])
    if kind == "cours":
        own_skills = {ref["id"] for ref in record["skills"]}
        related = [row for row in catalogue.records["cours"] if row["id"] != identifier and own_skills.intersection(ref["id"] for ref in row["skills"])]
        context["related"] = related[:3]
    elif kind == "parcours":
        context["courses"] = catalogue.ordered_courses(record)
        members = {row["id"] for row in context["courses"]}
        external = {ref["id"] for row in context["courses"] for ref in row["prerequisites"] if ref["id"] not in members}
        context["external_prerequisites"] = [catalogue.by_id[key] for key in sorted(external) if key in catalogue.by_id]
    elif kind == "competences":
        context["paths"] = [row for row in catalogue.records["parcours"] if any(ref["id"] == identifier for ref in row["skills"])]
    return render(request, f"core/{kind}_detail.html", context)


@require_GET
@public_view
@xframe_options_sameorigin
def resource_file(request, identifier):
    record = PublicCatalogue().get("ressources", identifier)
    key = managed_file_key(record["url"])
    if not key or record["resource_type"] != "DocumentPDF":
        raise Http404
    try:
        file = default_storage.open(key, "rb")
    except (FileNotFoundError, OSError) as exc:
        raise Http404 from exc
    return FileResponse(file, as_attachment=request.GET.get("download") == "1", filename=record["filename"] or "support.pdf", content_type="application/pdf")


def sparql_table(result, catalogue=None):
    links = {row["uri"]: row["public_url"] for row in catalogue.by_id.values()} if catalogue else {}
    columns = result.get("head", {}).get("vars", [])
    rows = []
    for binding in result.get("results", {}).get("bindings", []):
        cells = []
        for column in columns:
            cell = dict(binding.get(column, {}))
            value = cell.get("value", "")
            cell["bound"] = column in binding
            cell["language"] = cell.get("xml:lang", "")
            cell["display"] = "edu:" + value[len(settings.SEMANTIC_NAMESPACE):] if cell.get("type") == "uri" and value.startswith(settings.SEMANTIC_NAMESPACE) else value
            cell["link"] = links.get(value, "") if cell.get("type") == "uri" else ""
            cells.append(cell)
        rows.append(cells)
    return columns, rows


@never_cache
@require_http_methods(["GET", "POST"])
def intelligent_search(request):
    samples = examples()
    selected = next((row for row in samples if row["id"] == request.GET.get("exemple")), samples[0])
    mode = request.POST.get("mode", "sparql" if "query" in request.POST else "ai") if request.method == "POST" else request.GET.get("mode", "ai")
    mode = "sparql" if mode == "sparql" else "ai"
    question_form = QuestionForm(request.POST if request.method == "POST" and mode == "ai" else None, initial={"question": request.GET.get("question", "")[:1000]})
    form = QueryForm(request.POST if request.method == "POST" and mode == "sparql" else None, initial={"query": selected["query"]})
    status = 200
    result = ai_result = None
    plan = None
    groups, columns, rows = [], [], []
    error = ""
    selected_id = selected["id"]
    if request.method == "POST" and mode == "ai":
        if question_form.is_valid():
            try:
                if not configured():
                    raise AISearchError("La recherche IA n’est pas encore activée. Explorez le catalogue ou utilisez le mode SPARQL ci-dessous.")
                check_rate_limit(request)
                catalogue = PublicCatalogue()
                plan = translate_question(question_form.cleaned_data["question"], catalogue)
                if plan.status == "ready":
                    ai_result = execute_query(plan.sparql)
                    if "entity" not in ai_result.get("head", {}).get("vars", []):
                        raise QueryError("La sélection ne contient pas les éléments attendus.")
                    groups = result_groups(ai_result, catalogue)
                    form = QueryForm(initial={"query": plan.sparql})
                    selected_id = ""
            except AISearchError as exc:
                error, status = str(exc), exc.status
            except QueryError:
                error, status = "La traduction n’a pas pu être exécutée. Essayez de préciser votre demande ou ouvrez le mode SPARQL.", 502
            except SemanticStoreError:
                error, status = "Le catalogue est momentanément indisponible. Votre question est conservée ; réessayez dans quelques instants.", 503
        else:
            status = 422
    elif request.method == "POST" and mode == "sparql":
        selected_id = next((row["id"] for row in samples if row["query"].strip() == request.POST.get("query", "").strip()), "")
        if form.is_valid():
            try:
                result = execute_query(form.cleaned_data["query"])
            except QueryError as exc:
                form.add_error("query", str(exc))
                status = 422
            except SemanticStoreError as exc:
                form.add_error("query", str(exc))
                status = 503
            else:
                try:
                    catalogue = PublicCatalogue()
                except SemanticStoreError:
                    catalogue = None
                columns, rows = sparql_table(result, catalogue)
        else:
            status = 422
    return render(request, "core/search.html", {
        "active": "search", "mode": mode, "ai_configured": configured(),
        "question_form": question_form, "suggestions": SUGGESTIONS, "search_error": error,
        "plan": plan, "ai_result": ai_result, "groups": groups,
        "match_count": sum(len(group["rows"]) for group in groups),
        "form": form, "examples": samples, "selected_example": selected_id,
        "result": result, "columns": columns, "rows": rows, "max_rows": MAX_ROWS,
        "advanced_open": mode == "sparql" or bool(request.GET.get("exemple")),
        "graphs": [{"name": label, "uri": graph_uri(key)} for key, label in [("catalogue", "Catalogue"), ("ontology", "Ontologie"), ("inferences", "Inférences")]],
        "namespace": settings.SEMANTIC_NAMESPACE,
    }, status=status)


@never_cache
@require_http_methods(["GET", "POST"])
def sparql_lab(request):
    # Les anciens favoris conservent l'accès direct au mode technique.
    if request.method == "POST":
        return intelligent_search(request)
    parameters = {"mode": "sparql"}
    if request.GET.get("exemple"):
        parameters["exemple"] = request.GET["exemple"]
    return redirect("/recherche/?" + urlencode(parameters))


@require_GET
def health(request):
    services = {"postgresql": "ok", "fuseki": "ok"}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        services["postgresql"] = "unavailable"
    try:
        SemanticStore().query("ASK {}")
    except SemanticStoreError:
        services["fuseki"] = "unavailable"
    healthy = all(value == "ok" for value in services.values())
    return JsonResponse(
        {"status": "ok" if healthy else "unavailable", "services": services},
        status=200 if healthy else 503,
    )
