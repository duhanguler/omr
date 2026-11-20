# Deploying & Publishing OMRKit

This guide covers publishing **OMRKit** to PyPI via tokenless OIDC Trusted Publishing, launching a free public live demo on **HuggingFace Spaces** or **Render**, and running the official **GHCR Docker** image.

---

## Live Demo

- **Hosted Public Demo (Render):** https://omrkit-studio.onrender.com/ (OpenAPI: https://omrkit-studio.onrender.com/docs)
- **PyPI Package:** https://pypi.org/project/omrkit/
- **Container Image:** `ghcr.io/duhanguler/omr:latest`

---

## 1. One-Click Free Live Demo on Render (Recommended)

`render.yaml` is included at the repository root and runs the full Python + OpenCV + ReportLab + Web Studio Docker image for free over HTTPS (supporting browser `getUserMedia` **Live Camera** scanning):

1. Open `https://dashboard.render.com/blueprint/new?repo=https://github.com/duhanguler/omr`
2. Click **Apply** — Render builds `Dockerfile` with `OMRKIT_DEMO_MODE=true` and `/api/health` health checks automatically.

---

## 2. Run via Official GHCR Docker Image (Zero Build)

Every tagged release publishes a ready-to-run image to GitHub Container Registry:

```bash
docker run -p 8000:8000 ghcr.io/duhanguler/omr:latest
# Open http://localhost:8000 (Studio) or http://localhost:8000/docs (OpenAPI)
```

To enable hosted public demo mode with abuse guardrails:

```bash
docker run -p 8000:8000 \
  -e OMRKIT_DEMO_MODE=true \
  -e OMRKIT_MAX_UPLOAD_MB=15 \
  -e OMRKIT_MAX_FILES_PER_SCAN=20 \
  -e OMRKIT_MAX_PDF_PAGES=25 \
  ghcr.io/duhanguler/omr:latest
```

---

## 3. Deploy to HuggingFace Spaces (Requires HF PRO for Docker SDK)

> **Note:** HuggingFace currently requires a **PRO** subscription to host `sdk: docker` Spaces on `cpu-basic`. For a 100% free Docker deployment, use **Render** above.

1. Create a new Space at `https://huggingface.co/new-space` (`SDK: Docker → Blank`, name `omrkit-studio`).
2. Create a **Write** access token at `https://huggingface.co/settings/tokens`.
3. In your GitHub repository (`Settings → Secrets and variables → Actions`):
   - **Repository Secret:** `HF_TOKEN` = `<your_hf_write_token>`
   - **Repository Variable:** `HF_SPACE_REPO` = `<your_hf_username>/omrkit-studio`
4. Run **Actions → Deploy Live Demo (HuggingFace Spaces) → Run workflow** (or push to `main`).

---

## 4. Publish `omrkit` to PyPI (OIDC Trusted Publishing — Zero API Tokens)

`.github/workflows/release.yml` uses PyPI's modern OpenID Connect **Trusted Publishing** standard:

1. Sign in to `https://pypi.org/manage/account/publishing/` and add a **Pending Publisher**:
   - **PyPI Project Name:** `omrkit`
   - **Owner:** `duhanguler`
   - **Repository name:** `omr`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
2. *(Optional)* Repeat on `https://test.pypi.org/manage/account/publishing/` with environment name `testpypi` to test dry-runs first.
3. In your GitHub repository (`Settings → Secrets and variables → Actions → Variables`):
   - Add `ENABLE_PYPI_PUBLISH` = `true` (enables automatic PyPI publishing on every `v*.*.*` git tag).
4. To publish the current version immediately without creating a new tag:
   - Open **Actions → Release → Run workflow**, choose `publish_target: pypi` (or `testpypi`), and click **Run workflow**.

Once published, anyone can install with:

```bash
pip install omrkit          # Core CV engine + PDF + ArUco + Sheet Generator + CLI
pip install "omrkit[all]"   # Includes Web Studio, FastAPI REST API & Excel exports
```
