"""Read/write job_applications.json."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPLICATIONS_PATH = ROOT / "job_applications.json"


def load_jobs() -> list[dict]:
    return json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))


def save_jobs(jobs: list[dict]) -> None:
    APPLICATIONS_PATH.write_text(
        json.dumps(jobs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def find_job_index(
    jobs: list[dict],
    *,
    url: str | None = None,
    company: str | None = None,
) -> int:
    if url:
        key = url.strip()
        for i, job in enumerate(jobs):
            if key in (job.get("url", "").strip(), job.get("apply_url", "").strip()):
                return i
        raise KeyError(f"Job not found: {url}")

    if not company:
        raise KeyError("company or url required")

    company_l = company.strip().lower()
    matches = [
        i for i, job in enumerate(jobs) if job.get("company", "").strip().lower() == company_l
    ]
    if not matches:
        raise KeyError(f"Job not found: {company}")
    if len(matches) > 1:
        raise KeyError(f"Multiple jobs for {company} — pass url to disambiguate")
    return matches[0]


def mark_applied(
    company: str,
    applied_date: str | None = None,
    url: str | None = None,
) -> dict:
    jobs = load_jobs()
    idx = find_job_index(jobs, url=url, company=company)
    job = jobs[idx]
    job["status"] = "Applied"
    job["date_applied"] = applied_date or date.today().isoformat()
    note = f"Applied {job['date_applied']} via job-applier UI."
    existing = job.get("notes", "")
    if "Applied" not in existing:
        job["notes"] = f"{existing} {note}".strip() if existing else note
    jobs[idx] = job
    save_jobs(jobs)
    return job


def get_job(*, url: str | None = None, company: str | None = None) -> dict:
    jobs = load_jobs()
    return jobs[find_job_index(jobs, url=url, company=company)]
