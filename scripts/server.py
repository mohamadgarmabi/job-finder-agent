#!/usr/bin/env python3
"""Local UI server for job applications."""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
SCRIPTS_DIR = ROOT / "scripts"
PROFILE_PATH = ROOT / "career_profile.md"

sys.path.insert(0, str(SCRIPTS_DIR))

from job_store import load_jobs, mark_applied, update_status  # noqa: E402

PORT = 8765
_fill_lock = threading.Lock()
_fill_running: set[str] = set()
_search_lock = threading.Lock()
_search_running = False
_last_search_result: dict | None = None


def filter_jobs(
    jobs: list[dict],
    status: str | None,
    date_field: str,
    date_from: str | None,
    date_to: str | None,
    query: str | None,
    country: str | None = None,
) -> list[dict]:
    result = jobs

    if status and status != "all":
        result = [j for j in result if j.get("status") == status]

    if query:
        q = query.lower().strip()
        result = [
            j
            for j in result
            if q in j.get("company", "").lower()
            or q in j.get("title", "").lower()
            or q in j.get("notes", "").lower()
        ]

    if country and country != "all":
        c = country.lower()
        result = [
            j
            for j in result
            if c in (j.get("country") or "").lower()
            or c in (j.get("location") or "").lower()
        ]

    field = "date_applied" if date_field == "applied" else "date_found"
    if date_from:
        result = [j for j in result if (j.get(field) or "") >= date_from]
    if date_to:
        result = [j for j in result if (j.get(field) or "") <= date_to]

    return sorted(
        result,
        key=lambda j: (
            -(j.get("match_score") or 0),
            j.get("date_found") or "",
            j.get("company") or "",
        ),
    )


def parse_profile_contact() -> dict[str, str]:
    if not PROFILE_PATH.is_file():
        return {}
    text = PROFILE_PATH.read_text(encoding="utf-8")
    contact: dict[str, str] = {}
    in_contact = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower() == "## contact":
            in_contact = True
            continue
        if in_contact and stripped.startswith("## "):
            break
        if not in_contact or not stripped.startswith("- "):
            continue
        body = stripped[2:]
        if ":" not in body:
            continue
        key, val = body.split(":", 1)
        key = key.strip().lower()
        val = val.strip().strip("<>").strip()
        if val and val != "<!-- Fill in before applying -->":
            contact[key] = val
    name_m = re.search(r"^## name\s*\n+(.+)$", text, re.M | re.I)
    if name_m:
        contact.setdefault("name", name_m.group(1).strip())
    return contact


def merge_autofill(job: dict) -> dict[str, str]:
    profile = parse_profile_contact()
    autofill = dict(job.get("autofill") or {})
    defaults = {
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""),
        "github": profile.get("github", ""),
        "location": job.get("location") or profile.get("location", ""),
        "resume": autofill.get("resume", "resume.pdf"),
    }
    for key, val in defaults.items():
        autofill.setdefault(key, val)
    return {k: v for k, v in autofill.items() if v}


def build_copy_fields(job: dict) -> dict:
    autofill = merge_autofill(job)
    answers = job.get("application_answers") or {}
    cover = (job.get("cover_letter_draft") or "").strip()

    contact_labels = {
        "name": "Name",
        "email": "Email",
        "phone": "Phone",
        "linkedin": "LinkedIn",
        "github": "GitHub",
        "location": "Location",
        "resume": "Resume file",
    }
    contact = [
        {"key": key, "label": contact_labels[key], "value": autofill[key]}
        for key in contact_labels
        if autofill.get(key)
    ]

    answer_labels = {
        "location": "Location / relocation",
        "salary_expectation": "Salary",
        "english_level": "English level",
        "visa_relocate_interest": "Visa / relocation",
        "years_experience": "Experience",
        "why_role": "Why this role",
        "why_dualentry": "Why this company",
        "est_overlap": "Timezone overlap",
    }
    answer_rows = []
    for key, val in answers.items():
        if not val:
            continue
        label = answer_labels.get(key, key.replace("_", " ").title())
        answer_rows.append({"key": key, "label": label, "value": val})

    return {
        "contact": contact,
        "cover_letter": cover,
        "answers": answer_rows,
        "paste_sheet": build_paste_sheet(job, autofill, cover, answer_rows),
    }


def build_paste_sheet(
    job: dict,
    autofill: dict[str, str],
    cover: str,
    answer_rows: list[dict],
) -> str:
    lines = [
        f"{job.get('company', '')} — {job.get('title', '')}",
        f"URL: {job.get('apply_url') or job.get('url', '')}",
        f"Resume: upload {autofill.get('resume', 'resume.pdf')} | Submit: you click Apply",
        "",
        "--- CONTACT ---",
    ]
    for key in ("name", "email", "phone", "linkedin", "github"):
        if autofill.get(key):
            lines.append(autofill[key])
    if autofill.get("location"):
        lines.append(f"Location: {autofill['location']}")
    if cover:
        lines.extend(["", "--- COVER LETTER ---", cover])
    if answer_rows:
        lines.extend(["", "--- SHORT ANSWERS ---"])
        for row in answer_rows:
            lines.append(f"{row['label']}: {row['value']}")
    return "\n".join(lines).strip()


def public_job(job: dict) -> dict:
    copy_fields = build_copy_fields(job)
    return {
        "id": job.get("url"),
        "company": job.get("company"),
        "title": job.get("title"),
        "status": job.get("status"),
        "date_found": job.get("date_found"),
        "date_applied": job.get("date_applied"),
        "date_skipped": job.get("date_skipped"),
        "date_rejected": job.get("date_rejected"),
        "match_score": job.get("match_score"),
        "match_breakdown": job.get("match_breakdown"),
        "apply_url": job.get("apply_url") or job.get("url"),
        "url": job.get("url"),
        "relocate": job.get("relocate"),
        "country": job.get("country"),
        "location": job.get("location"),
        "has_autofill": bool(job.get("autofill")),
        "has_cover_letter": bool(job.get("cover_letter_draft")),
        "notes": job.get("notes", ""),
        "copy_fields": copy_fields,
    }


def start_fill(company: str, url: str | None = None) -> tuple[bool, str]:
    key = url or company
    with _fill_lock:
        if key in _fill_running:
            return False, "Already filling this form — wait a few seconds."
        _fill_running.add(key)

    def task() -> None:
        try:
            from fill_application import run
            from job_store import get_job

            job = get_job(url=url, company=company)
            run(job, headless=False, keep_open=False, detach=True)
        except Exception as exc:
            print(f"[fill] {company}: {exc}", file=sys.stderr)
        finally:
            with _fill_lock:
                _fill_running.discard(key)

    threading.Thread(target=task, daemon=True).start()
    return True, "Browser opened — form is being filled. Submit manually when ready."


def run_search(country: str = "all") -> tuple[bool, dict | str]:
    global _search_running, _last_search_result

    with _search_lock:
        if _search_running:
            return False, "Search already running — wait a few seconds."
        _search_running = True

    try:
        from job_finder import run_job_finder_skill

        result = run_job_finder_skill(country=country or "all")
        _last_search_result = result
        return True, result
    except Exception as exc:
        print(f"[search] {exc}", file=sys.stderr)
        return False, str(exc)
    finally:
        with _search_lock:
            _search_running = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _serve_static(self, rel_path: str) -> None:
        path = (UI_DIR / rel_path).resolve()
        if not str(path).startswith(str(UI_DIR.resolve())) or not path.is_file():
            self.send_error(404)
            return
        content = path.read_bytes()
        mime, _ = mimetypes.guess_type(str(path))
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._serve_static("index.html")
            return

        if path.startswith("/static/"):
            self._serve_static(path.removeprefix("/static/"))
            return

        if path == "/api/jobs":
            qs = parse_qs(parsed.query)
            jobs = filter_jobs(
                load_jobs(),
                status=(qs.get("status", [None])[0]),
                date_field=(qs.get("date_field", ["found"])[0] or "found"),
                date_from=(qs.get("date_from", [None])[0]),
                date_to=(qs.get("date_to", [None])[0]),
                query=(qs.get("q", [None])[0]),
                country=(qs.get("country", [None])[0]),
            )
            self._send_json({"jobs": [public_job(j) for j in jobs]})
            return

        if path == "/api/countries":
            from linkedin_jobs import COUNTRY_OPTIONS

            self._send_json({"countries": COUNTRY_OPTIONS})
            return

        if path == "/api/fill-status":
            self._send_json({"running": sorted(_fill_running)})
            return

        if path == "/api/search-status":
            self._send_json({"running": _search_running, "last": _last_search_result})
            return

        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json()

        if path == "/api/jobs/mark-applied":
            company = (body.get("company") or "").strip()
            url = (body.get("url") or body.get("id") or "").strip() or None
            if not company and not url:
                self._send_json({"ok": False, "error": "company or url required"}, 400)
                return
            try:
                job = mark_applied(company, body.get("date_applied"), url=url)
                self._send_json({"ok": True, "job": public_job(job)})
            except KeyError as exc:
                self._send_json({"ok": False, "error": str(exc)}, 404)
            return

        if path == "/api/jobs/update-status":
            company = (body.get("company") or "").strip()
            url = (body.get("url") or body.get("id") or "").strip() or None
            status = (body.get("status") or "").strip()
            if not company and not url:
                self._send_json({"ok": False, "error": "company or url required"}, 400)
                return
            if status not in ("Skipped", "Rejected", "To Apply", "Interview"):
                self._send_json({"ok": False, "error": "status must be Skipped or Rejected"}, 400)
                return
            try:
                note = (body.get("note") or "").strip() or None
                suffix = {
                    "Skipped": "Skipped via UI — not applying.",
                    "Rejected": "Rejected via UI — not interested.",
                    "To Apply": "Moved back to To Apply via UI.",
                    "Interview": "Marked as Interview via UI.",
                }.get(status, f"Status set to {status} via UI.")
                if note:
                    suffix = f"{suffix} Reason: {note}"
                job = update_status(company, status, url=url, note_suffix=suffix)
                self._send_json({"ok": True, "job": public_job(job)})
            except (KeyError, ValueError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, 404)
            return

        if path == "/api/jobs/fill":
            company = (body.get("company") or "").strip()
            url = (body.get("url") or body.get("id") or "").strip() or None
            if not company and not url:
                self._send_json({"ok": False, "error": "company or url required"}, 400)
                return
            ok, message = start_fill(company, url=url)
            self._send_json({"ok": ok, "message": message})
            return

        if path == "/api/jobs/search":
            country = (body.get("country") or "all").strip()
            ok, payload = run_search(country=country)
            if not ok:
                self._send_json({"ok": False, "message": payload})
                return
            self._send_json({"ok": True, "result": payload})
            return

        self.send_error(404)


def main() -> None:
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"\n{'=' * 50}")
    print(f"  Job Applier UI  →  {url}")
    print(f"{'=' * 50}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
