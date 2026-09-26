"""Resend email: content, attachments, retries and failure handling - offline (fake HTTP post)."""
import base64

import httpx
import pytest

from captable_app import notify
from captable_app.calc import calculate
from captable_app.models import ResolvedInput
from captable_app.pdf_report import round_labels
from captable_app.pipeline import RunResult

from conftest import make_cap, make_inputs


class FakeResp:
    def __init__(self, code, body):
        self.status_code, self._body, self.text = code, body, str(body)

    def json(self):
        return self._body


class FakePost:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers, json, timeout):
        self.calls.append((url, headers, json))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def run(tmp_path):
    cap = make_cap()
    inp = make_inputs(resolved=[ResolvedInput("Check size", 500.0, "User input (--check-size)")])
    res = calculate(cap, inp)
    pdf, xlsx = tmp_path / "r.pdf", tmp_path / "r.xlsx"
    pdf.write_bytes(b"%PDF-1.4 test")
    xlsx.write_bytes(b"PK xlsx")
    return RunResult("calculated", cap.company, round_labels(cap)[0], str(xlsx), str(pdf), inp, [], res)


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    monkeypatch.delenv("RESEND_TO", raising=False)
    monkeypatch.delenv("RESEND_FROM", raising=False)


def test_no_key_means_no_email(run):
    post = FakePost()
    r = notify.send_results(run, post=post)
    assert not r.sent and "RESEND_API_KEY" in r.error and not post.calls


def test_sends_to_info_with_pdf_and_workbook(monkeypatch, run):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    post = FakePost(FakeResp(200, {"id": "msg_1"}))
    r = notify.send_results(run, job_id="ab" * 16, post=post)
    assert r.sent and r.message_id == "msg_1" and r.to == ["Info@tencapital.group"]
    url, headers, payload = post.calls[0]
    assert url == notify.ENDPOINT and headers["Authorization"] == "Bearer re_test"
    assert payload["to"] == ["Info@tencapital.group"]
    assert "5.00% basic" in payload["subject"] and "TestCo" in payload["subject"]
    names = [a["filename"] for a in payload["attachments"]]
    assert names == ["r.pdf", "r.xlsx"]
    assert base64.b64decode(payload["attachments"][0]["content"]) == b"%PDF-1.4 test"
    assert "5.000%" in payload["html"] and "re_test" not in payload["html"] + payload["text"]


def test_blocked_run_email_lists_missing_inputs(monkeypatch, run):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    run.status, run.result = "blocked", None
    run.inputs.missing = ["Check size: ambiguous open allocation"]
    post = FakePost(FakeResp(200, {"id": "m"}))
    notify.send_results(run, post=post)
    p = post.calls[0][2]
    assert "unable to calculate" in p["subject"] and "Unable to calculate" in p["html"]
    assert "Check size: ambiguous open allocation" in p["text"]
    assert "%" not in p["subject"]


def test_retries_server_errors_but_not_rejections(monkeypatch, run):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    post = FakePost(httpx.ConnectError("x"), FakeResp(503, {"message": "busy"}), FakeResp(200, {"id": "ok"}))
    assert notify.send_results(run, post=post).sent and len(post.calls) == 3
    post2 = FakePost(FakeResp(403, {"message": "domain not verified"}))
    r = notify.send_results(run, post=post2)
    assert not r.sent and len(post2.calls) == 1 and "domain not verified" in r.note


def test_recipients_and_sender_configurable(monkeypatch):
    monkeypatch.setenv("RESEND_TO", "a@x.com, b@y.com,")
    monkeypatch.setenv("RESEND_FROM", "Me <me@x.com>")
    assert notify.recipients() == ["a@x.com", "b@y.com"] and notify.sender() == "Me <me@x.com>"
