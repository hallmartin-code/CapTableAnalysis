"""Web app: open access, upload -> blocked report -> rerun with inputs -> downloads.  No AI calls."""
import time

import pytest
from fastapi.testclient import TestClient

from conftest import CAP_XLSX, DECK_PPTX, real_sources



@pytest.fixture
def client(monkeypatch, tmp_path):
    from captable_app import web
    monkeypatch.setattr(web, "JOBS_DIR", str(tmp_path))
    with TestClient(web.app) as c:
        yield c


@pytest.fixture(scope="module")
def small_deck(tmp_path_factory):
    """The supplied deck with its media blanked: same slides and text, a few hundred KB instead of 123 MB.
    Streams the zip entry by entry so the large file is never held in memory at once."""
    import shutil
    import zipfile
    out = tmp_path_factory.mktemp("deck") / "deck.pptx"
    with zipfile.ZipFile(DECK_PPTX) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            if info.filename.startswith("ppt/media/"):
                dst.writestr(info.filename, b"")
            else:
                with src.open(info) as fin, dst.open(info.filename, "w") as fout:
                    shutil.copyfileobj(fin, fout)
    return str(out)


def _wait(client, url):
    job_id = url.rstrip("/").split("/")[-1]
    for _ in range(240):
        if client.get(f"/jobs/{job_id}/status").json()["status"] in ("done", "error"):
            return job_id
        time.sleep(0.25)
    raise AssertionError("job did not finish")


def test_pages_are_open_without_login(client):
    assert client.get("/healthz").json() == {"ok": True}
    r = client.get("/")
    assert r.status_code == 200 and "www-authenticate" not in r.headers


def test_rejects_wrong_file_types(client):
    r = client.post("/analyze", files={"cap_table": ("a.csv", b"x"), "deck": ("d.pptx", b"x")})
    assert r.status_code == 400


@real_sources
def test_upload_blocked_then_rerun_calculates(client, small_deck):
    with open(CAP_XLSX, "rb") as c, open(small_deck, "rb") as d:
        r = client.post("/analyze", follow_redirects=False,
                        files={"cap_table": ("cap.xlsx", c.read()), "deck": ("deck.pptx", d.read())},
                        data={"placeholder": "release"})
    assert r.status_code == 303, r.text
    job = _wait(client, r.headers["location"])
    page = client.get(f"/jobs/{job}").text
    assert "Unable to calculate" in page and "Check size" in page
    assert "%" not in page.split("Top data issues")[0].split("Unable to calculate")[1]

    r2 = client.post(f"/jobs/{job}/rerun", follow_redirects=False,
                     data={"check_size": "900,000", "commitments_in_before": "yes", "placeholder": "release"})
    job2 = _wait(client, r2.headers["location"])
    page2 = client.get(f"/jobs/{job2}").text
    assert "7.040%" in page2 and "6.152%" in page2
    pdf = client.get(f"/jobs/{job2}/download/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get(f"/jobs/{job2}/download/xlsx").status_code == 200
    assert client.get(f"/jobs/{job2}/download/../../etc").status_code == 404


def test_ui_pages_render_with_design_and_real_logo(client):
    html = client.get("/").text
    for s in ("Cap Table + Deck", "dropzone", 'name="cap_table"', 'name="deck"', "Run ownership analysis",
              "/static/logo.png", "--navy-950"):
        assert s in html
    assert "gmail.com" not in html
    logo = client.get("/static/logo.png")
    assert logo.status_code == 200 and logo.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_blocked_messages_name_form_fields_not_cli_flags():
    from captable_app.web_ui import web_wording
    msg = web_wording("Check size: ambiguous. Supply --check-size.")
    assert "--" not in msg and "Check size" in msg


def test_favicons_are_public_and_linked(client):
    ico = client.get("/favicon.ico")
    assert ico.status_code == 200 and ico.headers["content-type"] == "image/x-icon"
    for path in ("/public/favicon-32x32.png", "/public/icon.png", "/public/apple-touch-icon.png"):
        r = client.get(path)
        assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n", path
    html = client.get("/").text
    assert 'rel="icon" href="/favicon.ico"' in html and 'rel="apple-touch-icon"' in html
    assert client.get("/public/../.env").status_code == 404
