from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.testclient import TestClient

from backend.shared.static_serving import (
    IMMUTABLE_CACHE_CONTROL,
    REVALIDATE_CACHE_CONTROL,
    ImmutableStaticFiles,
    SelectiveGZipMiddleware,
    revalidating_file_response,
)


def test_hashed_assets_are_immutable_and_nosniff(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app-abc123.js").write_text("console.log('ok')", encoding="utf-8")

    app = FastAPI()
    app.mount("/assets", ImmutableStaticFiles(directory=assets), name="assets")

    response = TestClient(app).get("/assets/app-abc123.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == IMMUTABLE_CACHE_CONTROL
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-type"].startswith("application/javascript")


def test_index_and_root_public_files_must_revalidate(tmp_path):
    index = tmp_path / "index.html"
    index.write_text("<div id='root'></div>", encoding="utf-8")
    app = FastAPI()

    @app.get("/")
    def root():
        return revalidating_file_response(index)

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == REVALIDATE_CACHE_CONTROL
    assert response.headers["x-content-type-options"] == "nosniff"


def test_regular_responses_are_gzipped_when_requested():
    app = FastAPI()
    app.add_middleware(SelectiveGZipMiddleware, minimum_size=100)

    @app.get("/large")
    def large():
        return PlainTextResponse("x" * 2000)

    response = TestClient(app).get(
        "/large",
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["vary"] == "Accept-Encoding"
    assert response.text == "x" * 2000


def test_sse_is_never_gzipped_or_buffered():
    app = FastAPI()
    app.add_middleware(SelectiveGZipMiddleware, minimum_size=1)

    @app.get("/api/events")
    def events():
        return StreamingResponse(
            iter(["event: ping\ndata: {}\n\n"]),
            media_type="text/event-stream",
        )

    response = TestClient(app).get(
        "/api/events",
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.text == "event: ping\ndata: {}\n\n"
