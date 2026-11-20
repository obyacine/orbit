import httpx

from app.plane_client import PlaneClient


def _client(handler) -> PlaneClient:
    return PlaneClient(
        base_url="http://plane.test",
        api_key="k",
        workspace_slug="ws",
        transport=httpx.MockTransport(handler),
    )


def test_get_all_follows_cursor_pagination():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["X-Api-Key"] == "k"
        if "cursor" not in request.url.params:
            return httpx.Response(200, json={"results": [{"id": 1}], "next_cursor": "100:1:0", "next_page_results": True})
        return httpx.Response(200, json={"results": [{"id": 2}], "next_cursor": "100:2:0", "next_page_results": False})

    with _client(handler) as plane:
        items = plane.list_issues("p1")

    assert [i["id"] for i in items] == [1, 2]
    assert calls[0].url.path == "/api/v1/workspaces/ws/projects/p1/work-items/"
    assert calls[1].url.params["cursor"] == "100:1:0"


def test_non_paginated_list_is_returned_as_is():
    with _client(lambda r: httpx.Response(200, json=[{"id": "a"}])) as plane:
        assert plane.list_members("p1") == [{"id": "a"}]
