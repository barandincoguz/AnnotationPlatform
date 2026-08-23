from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.shared.body_limit import RequestBodyLimitMiddleware


def test_rejects_oversized_body_before_route_runs():
    called = False
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=10)

    @app.post("/upload")
    def upload():
        nonlocal called
        called = True
        return {"ok": True}

    with TestClient(app) as client:
        response = client.post("/upload", content=b"x" * 11)

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "request_body_too_large"
    assert called is False


def test_allows_body_at_limit():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=10)

    @app.post("/upload")
    def upload():
        return {"ok": True}

    with TestClient(app) as client:
        response = client.post("/upload", content=b"x" * 10)

    assert response.status_code == 200


def test_chunked_oversized_body_returns_413_not_parser_400():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=10)

    @app.post("/upload")
    async def upload(request: Request):
        await request.body()
        return {"ok": True}

    def chunks():
        yield b"123456"
        yield b"78901"

    with TestClient(app) as client:
        response = client.post("/upload", content=chunks())

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "request_body_too_large"
