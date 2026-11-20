"""Thin client for the Plane public API (/api/v1/), authenticated with X-Api-Key.

Orbit never touches Plane's database: everything goes through this client, so the
tracker stays swappable (Jira, GitHub Projects...) by reimplementing this module.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


class PlaneError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: str):
        super().__init__(f"Plane API {method} {path} -> {status}: {body[:500]}")
        self.status = status


class PlaneClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        workspace_slug: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        settings = get_settings()
        self.slug = workspace_slug or settings.plane_workspace_slug
        if not self.slug:
            raise ValueError("PLANE_WORKSPACE_SLUG is not set")
        self._http = httpx.Client(
            base_url=f"{(base_url or settings.plane_base_url).rstrip('/')}/api/v1/workspaces/{self.slug}/",
            headers={"X-Api-Key": api_key or settings.plane_api_key},
            timeout=30.0,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PlaneClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- low level

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._http.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise PlaneError(method, path, resp.status_code, resp.text)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def _get_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Follow Plane's cursor pagination (results / next_cursor / next_page_results)."""
        params = {"per_page": 100, **(params or {})}
        items: list[dict[str, Any]] = []
        while True:
            data = self._request("GET", path, params=params)
            if isinstance(data, list):  # some endpoints are not paginated
                return data
            items.extend(data.get("results", []))
            if not data.get("next_page_results"):
                return items
            params["cursor"] = data["next_cursor"]

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", path, json=payload)

    def _patch(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("PATCH", path, json=payload)

    # ---------------------------------------------------------------- projects

    def list_projects(self) -> list[dict[str, Any]]:
        return self._get_all("projects/")

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"projects/{project_id}/")

    def create_project(self, name: str, identifier: str, description: str = "") -> dict[str, Any]:
        return self._post(
            "projects/",
            {
                "name": name,
                "identifier": identifier,
                "description": description,
                "cycle_view": True,
                "module_view": True,
                "intake_view": True,
                "page_view": True,
            },
        )

    def delete_project(self, project_id: str) -> None:
        self._request("DELETE", f"projects/{project_id}/")

    def list_members(self, project_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/members/")

    # ---------------------------------------------------------------- states & labels

    def list_states(self, project_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/states/")

    def list_labels(self, project_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/labels/")

    def create_label(self, project_id: str, name: str, color: str) -> dict[str, Any]:
        return self._post(f"projects/{project_id}/labels/", {"name": name, "color": color})

    # ---------------------------------------------------------------- work items

    def list_issues(self, project_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/work-items/")

    def create_issue(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"projects/{project_id}/work-items/", payload)

    def update_issue(self, project_id: str, issue_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._patch(f"projects/{project_id}/work-items/{issue_id}/", payload)

    def list_comments(self, project_id: str, issue_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/work-items/{issue_id}/comments/")

    def add_comment(self, project_id: str, issue_id: str, html: str) -> dict[str, Any]:
        return self._post(f"projects/{project_id}/work-items/{issue_id}/comments/", {"comment_html": html})

    def list_activities(self, project_id: str, issue_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/work-items/{issue_id}/activities/")

    def list_relations(self, project_id: str, issue_id: str) -> Any:
        return self._request("GET", f"projects/{project_id}/work-items/{issue_id}/relations/")

    def add_relation(self, project_id: str, issue_id: str, relation_type: str, issue_ids: list[str]) -> Any:
        return self._post(
            f"projects/{project_id}/work-items/{issue_id}/relations/",
            {"relation_type": relation_type, "issues": issue_ids},
        )

    # ---------------------------------------------------------------- modules (epics)

    def list_modules(self, project_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/modules/")

    def create_module(
        self,
        project_id: str,
        name: str,
        description: str = "",
        start_date: str | None = None,
        target_date: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "description": description}
        if start_date and target_date:  # dated modules are phases (Waterfall / hybrid)
            payload |= {"start_date": start_date, "target_date": target_date}
        return self._post(f"projects/{project_id}/modules/", payload)

    def list_module_issues(self, project_id: str, module_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/modules/{module_id}/module-issues/")

    def add_issues_to_module(self, project_id: str, module_id: str, issue_ids: list[str]) -> Any:
        return self._post(f"projects/{project_id}/modules/{module_id}/module-issues/", {"issues": issue_ids})

    # ---------------------------------------------------------------- cycles (sprints / milestones)

    def list_cycles(self, project_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/cycles/")

    def create_cycle(self, project_id: str, name: str, start_date: str, end_date: str) -> dict[str, Any]:
        return self._post(
            f"projects/{project_id}/cycles/",
            {"name": name, "start_date": start_date, "end_date": end_date},
        )

    def update_cycle(self, project_id: str, cycle_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._patch(f"projects/{project_id}/cycles/{cycle_id}/", payload)

    def list_cycle_issues(self, project_id: str, cycle_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"projects/{project_id}/cycles/{cycle_id}/cycle-issues/")

    def add_issues_to_cycle(self, project_id: str, cycle_id: str, issue_ids: list[str]) -> Any:
        return self._post(f"projects/{project_id}/cycles/{cycle_id}/cycle-issues/", {"issues": issue_ids})
