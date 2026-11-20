# Copyright (c) 2026-present Orbit contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Proxy between the web app and the Orbit AI agent (ai-service).

The browser never talks to the agent: it calls these endpoints with its session, they check the
user's role in the project, then forward the call with the shared secret (X-Orbit-Token).
"""

import requests
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.db.models import APIToken, ProjectMember, ProjectUserProperty
from plane.app.views.base import BaseAPIView

_TIMEOUT_SECONDS = 180  # a report = platform reads + up to two LLM calls; a baseline push creates many objects
_READ = [ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST]
_WRITE = [ROLE.ADMIN, ROLE.MEMBER]


def _agent(method, path, payload=None, params=None):
    url = f"{settings.ORBIT_AI_SERVICE_URL.rstrip('/')}{path}"
    try:
        resp = requests.request(
            method,
            url,
            json=payload,
            params=params,
            headers={"X-Orbit-Token": settings.ORBIT_INTERNAL_TOKEN},
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return None, Response(
            {"error": "L'agent IA est injoignable. Vérifiez que le service ai-service est démarré."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    try:
        data = resp.json()
    except ValueError:
        data = {"error": resp.text[:500]}
    if resp.status_code >= 400:
        detail = data.get("detail") if isinstance(data, dict) else None
        return None, Response({"error": detail or data}, status=resp.status_code)
    return data, None


def _ensure_agent_member(slug, project_id):
    """The agent reads and writes through the public API with its own key: make it a member of the project."""
    token = APIToken.objects.filter(token=settings.ORBIT_AGENT_API_KEY, is_active=True).select_related("workspace").first()
    if not token or not token.workspace or token.workspace.slug != slug:
        return
    member, _ = ProjectMember.objects.get_or_create(
        project_id=project_id, member=token.user, defaults={"role": ROLE.ADMIN.value, "workspace": token.workspace}
    )
    if not member.is_active or member.role != ROLE.ADMIN.value:
        member.is_active, member.role = True, ROLE.ADMIN.value
        member.save(update_fields=["is_active", "role"])
    ProjectUserProperty.objects.get_or_create(project_id=project_id, user=token.user, workspace=token.workspace)


def _forward(method, path, payload=None, params=None):
    data, error = _agent(method, path, payload, params)
    return error or Response(data, status=status.HTTP_200_OK)


class OrbitAgentCatalogEndpoint(BaseAPIView):
    @allow_permission(_READ)
    def get(self, request, slug, project_id):
        return _forward("GET", "/methods")


class OrbitAgentMethodEndpoint(BaseAPIView):
    @allow_permission(_READ)
    def get(self, request, slug, project_id):
        return _forward("GET", f"/projects/{project_id}/method")

    @allow_permission([ROLE.ADMIN])
    def put(self, request, slug, project_id):
        payload = {**request.data, "updated_by": request.user.display_name}
        return _forward("PUT", f"/projects/{project_id}/method", payload)


class OrbitAgentAnalysisEndpoint(BaseAPIView):
    @allow_permission(_READ)
    def get(self, request, slug, project_id):
        _ensure_agent_member(slug, project_id)
        return _forward("GET", f"/projects/{project_id}/analysis")


class OrbitAgentReportsEndpoint(BaseAPIView):
    @allow_permission(_READ)
    def get(self, request, slug, project_id):
        params = {"type": request.query_params["type"]} if request.query_params.get("type") else None
        return _forward("GET", f"/projects/{project_id}/reports", params=params)


class OrbitAgentGenerateReportEndpoint(BaseAPIView):
    @allow_permission(_WRITE)
    def post(self, request, slug, project_id, report_type):
        if report_type not in ("progress", "situation"):
            return Response({"error": "Type de rapport inconnu"}, status=status.HTTP_400_BAD_REQUEST)
        _ensure_agent_member(slug, project_id)
        return _forward("POST", f"/projects/{project_id}/reports/{report_type}")


class OrbitAgentApproveReportEndpoint(BaseAPIView):
    @allow_permission(_WRITE)
    def post(self, request, slug, project_id, report_id):
        # A report can only be approved from the project it belongs to.
        report, error = _agent("GET", f"/reports/{report_id}")
        if error:
            return error
        if str(report.get("project_id")) != str(project_id):
            return Response({"error": "Rapport introuvable"}, status=status.HTTP_404_NOT_FOUND)
        payload = {"approved_by": request.user.display_name, "markdown": request.data.get("markdown")}
        return _forward("POST", f"/reports/{report_id}/approve", payload)


# ------------------------------------------------------------------ Module 1: brief -> baseline


class OrbitAgentBaselinesEndpoint(BaseAPIView):
    @allow_permission(_READ)
    def get(self, request, slug, project_id):
        return _forward("GET", f"/projects/{project_id}/baselines")


class OrbitAgentBaselineDraftEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN])
    def post(self, request, slug, project_id):
        payload = {"brief": request.data.get("brief", ""), "created_by": request.user.display_name}
        return _forward("POST", f"/projects/{project_id}/baseline/draft", payload)


def _baseline_of_project(baseline_id, project_id):
    baseline, error = _agent("GET", f"/projects/{project_id}/baselines")
    if error:
        return error
    if not any(b["id"] == str(baseline_id) for b in baseline):
        return Response({"error": "Baseline introuvable"}, status=status.HTTP_404_NOT_FOUND)
    return None


class OrbitAgentBaselineDetailEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN])
    def put(self, request, slug, project_id, baseline_id):
        error = _baseline_of_project(baseline_id, project_id)
        return error or _forward("PUT", f"/baselines/{baseline_id}", {"content": request.data.get("content")})


class OrbitAgentBaselineValidateEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN])
    def post(self, request, slug, project_id, baseline_id):
        error = _baseline_of_project(baseline_id, project_id)
        if error:
            return error
        _ensure_agent_member(slug, project_id)
        payload = {"validated_by": request.user.display_name, "content": request.data.get("content")}
        return _forward("POST", f"/baselines/{baseline_id}/validate", payload)
