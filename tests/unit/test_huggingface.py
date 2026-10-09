import httpx

from preprint_radar.http import HttpClient
from preprint_radar.sources.huggingface import HUGGINGFACE_API_URL, fetch_likes


def test_fetch_likes_asks_each_page() -> None:
    asked: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        answers = {
            "/api/models/lab/fast-net": httpx.Response(200, json={"id": "lab/fast-net", "likes": 42}),
            "/api/datasets/lab/scenes": httpx.Response(200, json={"id": "lab/scenes", "likes": 3}),
            "/api/spaces/lab/demo": httpx.Response(404),
            "/api/models/lab/private": httpx.Response(401, json={"error": "Repository Not Found"}),
            "/api/models/lab/odd": httpx.Response(200, json={"id": "lab/odd"}),  # no likes
        }
        return answers.get(request.url.path, httpx.Response(503))

    pages = [
        "models/lab/fast-net",
        "datasets/lab/scenes",
        "spaces/lab/demo",
        "models/lab/private",
        "models/lab/odd",
        "models/lab/down",
        "models/lab/fast-net",
    ]
    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        found = fetch_likes(client, pages)

    assert HUGGINGFACE_API_URL.endswith("/api")
    assert len(asked) == 6  # each page once
    assert found.likes == {"models/lab/fast-net": 42, "datasets/lab/scenes": 3}
    # Gone (404, or 401 for a repository that does not exist); the others failed.
    assert found.missing == {"spaces/lab/demo", "models/lab/private"}
