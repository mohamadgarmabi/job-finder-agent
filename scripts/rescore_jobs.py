#!/usr/bin/env python3
"""Re-score all jobs in job_applications.json against resume_profile.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from resume_matcher import rescore_all_jobs  # noqa: E402

ROOT = SCRIPTS_DIR.parent
APPLICATIONS_PATH = ROOT / "job_applications.json"


def main() -> None:
    jobs = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    jobs = rescore_all_jobs(jobs)
    APPLICATIONS_PATH.write_text(
        json.dumps(jobs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    top = sorted(jobs, key=lambda j: j.get("match_score") or 0, reverse=True)[:8]
    print(f"Rescored {len(jobs)} jobs against resume.\n")
    for j in top:
        print(f"  {j.get('match_score', 0):>3}%  {j.get('company')} — {j.get('title', '')[:50]}")


if __name__ == "__main__":
    main()
