# Copyright (c) 2026-present Orbit contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views.orbit_agent import (
    OrbitAgentAnalysisEndpoint,
    OrbitAgentBaselineDetailEndpoint,
    OrbitAgentBaselineDraftEndpoint,
    OrbitAgentBaselineExportEndpoint,
    OrbitAgentBaselinesEndpoint,
    OrbitAgentBaselineValidateEndpoint,
    OrbitAgentApproveReportEndpoint,
    OrbitAgentCatalogEndpoint,
    OrbitAgentDocumentExtractEndpoint,
    OrbitAgentLibraryDocumentEndpoint,
    OrbitAgentLibraryEndpoint,
    OrbitAgentGenerateReportEndpoint,
    OrbitAgentMethodEndpoint,
    OrbitAgentReportsEndpoint,
)

_BASE = "workspaces/<str:slug>/projects/<uuid:project_id>/agent"

urlpatterns = [
    path(f"{_BASE}/library/", OrbitAgentLibraryEndpoint.as_view(), name="orbit-agent-library"),
    path(f"{_BASE}/library/<uuid:reference_id>/", OrbitAgentLibraryDocumentEndpoint.as_view(), name="orbit-agent-library-doc"),
    path(f"{_BASE}/documents/extract/", OrbitAgentDocumentExtractEndpoint.as_view(), name="orbit-agent-document-extract"),
    path(f"{_BASE}/baselines/", OrbitAgentBaselinesEndpoint.as_view(), name="orbit-agent-baselines"),
    path(f"{_BASE}/baselines/draft/", OrbitAgentBaselineDraftEndpoint.as_view(), name="orbit-agent-baseline-draft"),
    path(f"{_BASE}/baselines/<uuid:baseline_id>/", OrbitAgentBaselineDetailEndpoint.as_view(), name="orbit-agent-baseline"),
    path(
        f"{_BASE}/baselines/<uuid:baseline_id>/export/",
        OrbitAgentBaselineExportEndpoint.as_view(),
        name="orbit-agent-baseline-export",
    ),
    path(
        f"{_BASE}/baselines/<uuid:baseline_id>/validate/",
        OrbitAgentBaselineValidateEndpoint.as_view(),
        name="orbit-agent-baseline-validate",
    ),
    path(f"{_BASE}/methods/", OrbitAgentCatalogEndpoint.as_view(), name="orbit-agent-methods"),
    path(f"{_BASE}/method/", OrbitAgentMethodEndpoint.as_view(), name="orbit-agent-method"),
    path(f"{_BASE}/analysis/", OrbitAgentAnalysisEndpoint.as_view(), name="orbit-agent-analysis"),
    path(f"{_BASE}/reports/", OrbitAgentReportsEndpoint.as_view(), name="orbit-agent-reports"),
    path(
        f"{_BASE}/reports/<uuid:report_id>/approve/",
        OrbitAgentApproveReportEndpoint.as_view(),
        name="orbit-agent-report-approve",
    ),
    path(
        f"{_BASE}/reports/<str:report_type>/",
        OrbitAgentGenerateReportEndpoint.as_view(),
        name="orbit-agent-report-generate",
    ),
]
