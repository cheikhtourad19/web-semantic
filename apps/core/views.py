from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.semantic.services import SemanticStore, SemanticStoreError


@require_GET
def home(request):
    return render(request, "core/home.html")


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

