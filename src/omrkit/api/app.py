"""FastAPI application factory serving OMRKit REST API and compiled Web Studio SPA."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from omrkit.api.routes import router

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Create and configure the OMRKit FastAPI application."""
    app = FastAPI(
        title="OMRKit API & Studio",
        description=(
            "Modern Optical Mark Recognition API: ArUco/marker registration, hybrid "
            "confidence-scored bubble detection, printable PDF sheet generation, "
            "and Classical Test Theory exam psychometrics."
        ),
        version="2.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="studio-assets")

    index_html = STATIC_DIR / "index.html"

    @app.get("/", include_in_schema=False, response_model=None)
    def serve_root() -> FileResponse | HTMLResponse:
        if index_html.exists():
            return FileResponse(index_html)
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;padding:2rem;'>"
            "<h1>OMRKit v2.0 API is running</h1>"
            "<p>Interactive API docs: <a href='/docs'>/docs</a></p>"
            "<p>Build the Web Studio frontend via <code>cd studio && npm run build</code>.</p>"
            "</body></html>"
        )

    return app
