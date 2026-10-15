from collections import Counter
from functools import wraps
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils.http import urlencode
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods

from apps.semantic.catalogue import Catalogue, KINDS, LEVELS, RESOURCE_TYPES, deletion_blockers, get_kind, managed_file_key
from apps.semantic.services import SemanticStoreError
from .forms import EntityForm, StaffAuthenticationForm

logger = logging.getLogger(__name__)


def staff_view(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff or not request.user.is_active:
            raise PermissionDenied
        try:
            return view(request, *args, **kwargs)
        except SemanticStoreError:
            logger.exception("Fuseki indisponible dans le backoffice")
            return render(request, "backoffice/unavailable.html", shell_context(), status=503)
    return wrapped


def shell_context(active="dashboard", **extra):
    return {"navigation": list(KINDS.values()), "active": active, **extra}


class StaffLoginView(LoginView):
    template_name = "backoffice/login.html"
    authentication_form = StaffAuthenticationForm
    redirect_authenticated_user = True


@staff_view
@require_GET
def dashboard(request):
    snapshot = Catalogue().snapshot()
    records = {kind: snapshot.all(kind) for kind in KINDS}
    stats = [{"kind": config, "count": len(records[key])} for key, config in KINDS.items()]
    levels = Counter(course["level"] for course in records["cours"])
    total = len(records["cours"])
    distribution = [{"key": key, "label": label, "count": levels[key], "percent": round(levels[key] * 100 / total) if total else 0} for key, label in LEVELS.items()]
    recent = sorted(records["cours"], key=lambda row: row["modified"].timestamp() if row["modified"] else 0, reverse=True)[:5]
    needs = [
        {"count": sum(not row["resources"] for row in records["cours"]), "label": "cours sans support", "kind": "cours", "filter": "without_resource"},
        {"count": sum(not row["paths"] for row in records["cours"]), "label": "cours sans parcours", "kind": "cours", "filter": "without_path"},
        {"count": sum(not row["used_by"] for row in records["ressources"]), "label": "ressources non associées", "kind": "ressources", "filter": "unused"},
    ]
    return render(request, "backoffice/dashboard.html", shell_context(stats=stats, recent=recent, distribution=distribution, needs=needs, course_count=total, skill_count=len(records["competences"])))


@staff_view
@require_GET
def entity_list(request, kind):
    config = get_kind(kind)
    snapshot = Catalogue().snapshot()
    all_rows = snapshot.all(kind)
    rows = all_rows
    q = request.GET.get("q", "").strip()[:200]
    if q:
        rows = [row for row in rows if q.casefold() in f"{row['title']} {row['description']}".casefold()]
    selected = request.GET.get("filter", "")
    if kind == "cours":
        if selected in LEVELS:
            rows = [row for row in rows if row["level"] == selected]
        elif selected == "without_resource":
            rows = [row for row in rows if not row["resources"]]
        elif selected == "without_path":
            rows = [row for row in rows if not row["paths"]]
    elif kind == "ressources":
        if selected in RESOURCE_TYPES:
            rows = [row for row in rows if row["resource_type"] == selected]
        elif selected == "unused":
            rows = [row for row in rows if not row["used_by"]]
    sort = request.GET.get("sort", "title")
    if sort == "recent":
        rows = sorted(rows, key=lambda row: row["modified"].timestamp() if row["modified"] else 0, reverse=True)
    elif sort == "duration" and kind in ("cours", "parcours"):
        rows = sorted(rows, key=lambda row: row["duration"])
    filters = []
    options = LEVELS if kind == "cours" else RESOURCE_TYPES if kind == "ressources" else {}
    for key, label in options.items():
        field = "level" if kind == "cours" else "resource_type"
        filters.append({"key": key, "label": label, "count": sum(row[field] == key for row in all_rows)})
    page = Paginator(rows, 12).get_page(request.GET.get("page"))
    parameters = request.GET.copy()
    parameters.pop("page", None)
    return render(request, "backoffice/list.html", shell_context(kind, config=config, rows=page, total=len(all_rows), filtered_count=len(rows), q=q, selected_filter=selected, sort=sort, filters=filters, pagination_query=urlencode(parameters)))


@staff_view
@require_GET
def entity_detail(request, kind, identifier):
    config = get_kind(kind)
    snapshot = Catalogue().snapshot()
    record = snapshot.get(kind, identifier)
    course_details = [snapshot.get("cours", row["id"]) for row in record["courses"]] if kind == "parcours" else []
    return render(request, "backoffice/detail.html", shell_context(kind, config=config, record=record, courses=course_details))


@staff_view
@require_http_methods(["GET", "POST"])
def entity_edit(request, kind, identifier=None):
    config = get_kind(kind)
    repository = Catalogue()
    snapshot = repository.snapshot()
    record = snapshot.get(kind, identifier) if identifier else None
    initial = {}
    if not record and kind == "ressources" and request.GET.get("course"):
        course = snapshot.get("cours", request.GET["course"])
        initial["courses"] = [course["id"]]
    form = EntityForm(request.POST if request.method == "POST" else None, request.FILES or None, snapshot=snapshot, kind=kind, record=record, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            saved_id = repository.save(kind, form.cleaned_data, identifier)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Les modifications sont enregistrées." if record else f"« {form.cleaned_data['title']} » a été ajouté au catalogue.")
            return redirect("backoffice:detail", kind=kind, identifier=saved_id)
    return render(request, "backoffice/form.html", shell_context(kind, config=config, record=record, form=form), status=422 if request.method == "POST" and form.errors else 200)


@staff_view
@require_http_methods(["GET", "POST"])
def entity_delete(request, kind, identifier):
    config = get_kind(kind)
    repository = Catalogue()
    snapshot = repository.snapshot()
    record = snapshot.get(kind, identifier)
    error = None
    blockers = deletion_blockers(record)
    if request.method == "POST":
        try:
            repository.delete(kind, identifier, request.POST.get("version", ""))
        except ValidationError as exc:
            error = " ".join(exc.messages)
        else:
            messages.success(request, f"« {record['title']} » a été supprimé.")
            return redirect("backoffice:list", kind=kind)
    return render(request, "backoffice/delete.html", shell_context(kind, config=config, record=record, blockers=blockers, version=snapshot.version, error=error), status=422 if error else 200)


@staff_view
@require_GET
@xframe_options_sameorigin
def resource_file(request, identifier):
    record = Catalogue().snapshot().get("ressources", identifier)
    key = managed_file_key(record["url"])
    if not key:
        raise Http404
    try:
        file = default_storage.open(key, "rb")
    except (FileNotFoundError, OSError) as exc:
        raise Http404 from exc
    return FileResponse(file, as_attachment=request.GET.get("download") == "1", filename=record["filename"] or "support.pdf", content_type="application/pdf")
