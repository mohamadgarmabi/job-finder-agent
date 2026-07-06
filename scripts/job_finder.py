#!/usr/bin/env python3
"""
job-finder skill implementation.

Follows .agents/skills/job-finder/SKILL.md steps 1–7.
Entry points:
  python scripts/job_finder.py [--country Germany]
  UI "Find new jobs" → POST /api/jobs/search
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

PREFERENCES_PATH = ROOT / "job_preferences.md"
PROFILE_PATH = ROOT / "career_profile.md"
STATE_PATH = ROOT / "finder_state.json"
APPLICATIONS_PATH = ROOT / "job_applications.json"
SKILL_NAME = "job-finder"

TECH_KEYWORDS = [
    "react",
    "next.js",
    "nextjs",
    "typescript",
    "frontend",
    "front-end",
    "front end",
    "node.js",
    "nodejs",
    "remix",
    "solidjs",
    "solid.js",
    "javascript",
    "fullstack",
    "full-stack",
    "full stack",
]

RELOCATE_KEYWORDS = [
    "visa sponsorship",
    "visa support",
    "sponsor visa",
    "sponsors visa",
    "relocation package",
    "relocation support",
    "relocation assistance",
    "relocation and visa",
    "visa and relocation",
    "help with relocation",
    "relocation offered",
    "relocate to",
    "relocation to",
    "work permit",
    "immigration support",
    "tech visa",
]

NEGATIVE_RELOCATE = [
    "cannot provide visa",
    "no visa sponsorship",
    "unable to sponsor",
    "not able to sponsor",
    "without visa sponsorship",
]

ROLE_BLOCKLIST = [
    "talent acquisition",
    "recruiter",
    "food developer",
    "e-commerce manager",
    "product line manager",
    "data scientist",
    "data analyst",
    "copywriter",
    "customer success",
    "account manager",
    "sales ",
]


def strip_html(text: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_markdown_sections(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    if not path.exists():
        return sections
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current and line.strip().startswith("- "):
            value = line.strip()[2:].strip()
            if value and not value.startswith("<!--"):
                sections[current].append(value)
    return sections


def parse_preferences() -> dict[str, list[str]]:
    return parse_markdown_sections(PREFERENCES_PATH)


def parse_career_profile() -> dict[str, list[str]]:
    return parse_markdown_sections(PROFILE_PATH)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_json(url: str, timeout: int = 30) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "job-finder-skill/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_key(company: str, title: str) -> str:
    title_n = re.sub(r"[^\w\s]", " ", title.lower())
    title_n = re.sub(r"\s+", " ", title_n).strip()
    return f"{company.strip().lower()}|{title_n}"


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/").lower().split("?")[0]


def existing_keys(jobs: list[dict]) -> tuple[set[str], set[str]]:
    by_pair: set[str] = set()
    by_url: set[str] = set()
    for job in jobs:
        by_pair.add(normalize_key(job.get("company", ""), job.get("title", "")))
        for field in ("url", "apply_url"):
            if job.get(field):
                by_url.add(normalize_url(job[field]))
    return by_pair, by_url


def is_duplicate(job: dict, by_pair: set[str], by_url: set[str]) -> bool:
    if normalize_key(job["company"], job["title"]) in by_pair:
        return True
    for field in ("url", "apply_url"):
        if job.get(field) and normalize_url(job[field]) in by_url:
            return True
    return False


def red_line_from_preferences(blob: str, red_lines: list[str]) -> str | None:
    lower = blob.lower()
    for line in red_lines:
        ll = line.lower()
        if "php" in ll and re.search(r"\bphp\b", lower) and "phpstorm" not in lower:
            return "php (red line)"
        if ("on-site" in ll or "onsite" in ll or "in-office" in ll) and "hybrid" not in lower:
            if re.search(r"\b(on[- ]site only|fully on[- ]site|100% on[- ]site|in[- ]office only)\b", lower):
                return "on-site only (red line)"
            if re.search(r"\bon[- ]site\b", lower) and "remote" not in lower and "hybrid" not in lower:
                return "on-site (red line)"
        if "legacy" in ll and "legacy" in lower:
            return "legacy tech (red line)"
        if "jquery" in ll and "jquery" in lower:
            return "jquery (red line)"
    return None


def relocate_hint(blob: str) -> str | None:
    lower = blob.lower()
    for neg in NEGATIVE_RELOCATE:
        if neg in lower:
            return None
    for phrase in RELOCATE_KEYWORDS:
        if phrase in lower:
            return phrase
    if re.search(r"\bvisa\b", lower) and "sponsor" in lower:
        return "visa sponsorship"
    if re.search(r"\brelocation\b", lower):
        return "relocation"
    if re.search(r"\brelocate\b", lower):
        return "relocate"
    return None


def tech_hits(blob: str, keywords: list[str]) -> list[str]:
    lower = blob.lower()
    hits: list[str] = []
    for kw in TECH_KEYWORDS + [k.lower() for k in keywords]:
        if kw in lower and kw not in hits:
            hits.append(kw)
    return hits


def role_tech_hits(title: str, tags: list[str], description: str, keywords: list[str], target_roles: list[str]) -> list[str]:
    title_blob = f"{title} {' '.join(tags)}".lower()
    title_hits = tech_hits(title_blob, keywords)
    if title_hits:
        return title_hits

    role_blob = " ".join(target_roles).lower()
    if role_blob and any(r.split()[0] in title.lower() for r in target_roles if r):
        desc_hits = tech_hits(strip_html(description).lower(), keywords)
        if desc_hits:
            return desc_hits

    if re.search(r"\b(developer|engineer|frontend|full[\s-]?stack|software)\b", title.lower()):
        return tech_hits(strip_html(description).lower(), keywords)
    return []


def score_job(blob: str, tech_hits_list: list[str], has_relocate: bool, title: str = "", description: str = "", tags: list | None = None) -> int:
    from resume_matcher import score_job_against_resume

    score, _ = score_job_against_resume(
        title=title,
        description=description,
        tags=tags or list(tech_hits_list),
        relocate=has_relocate,
    )
    return score


def build_search_keywords(prefs: dict[str, list[str]], profile: dict[str, list[str]]) -> str:
    parts: list[str] = []
    for key in ("tech_stack", "search_keywords"):
        for term in prefs.get(key, []):
            t = term.lower().strip()
            if t and t not in parts:
                parts.append(t)
    for role in profile.get("target_roles", []):
        for word in role.lower().split():
            if len(word) > 3 and word not in parts:
                parts.append(word)
    for required in ("react", "typescript", "visa", "relocation"):
        if required not in parts:
            parts.append(required)
    return " ".join(parts[:12])


def raw_to_job(
    *,
    company: str,
    title: str,
    url: str,
    description: str,
    tags: list[str],
    remote: bool | None,
    source: str,
    keywords: list[str],
    target_roles: list[str],
    red_lines: list[str],
    relocate_only: bool,
    country: str = "",
    location: str = "",
) -> dict | None:
    plain = strip_html(description)
    blob = f"{title} {company} {plain} {' '.join(tags)}".lower()

    if any(block in title.lower() for block in ROLE_BLOCKLIST):
        return None
    if red_line_from_preferences(blob, red_lines):
        return None

    hits = role_tech_hits(title, tags, description, keywords, target_roles)
    if not hits:
        return None

    relocate = relocate_hint(blob)
    if relocate_only and not relocate:
        return None

    apply_url = url
    if "arbeitnow.com" in url and not url.endswith("/apply"):
        apply_url = url.rstrip("/") + "/apply"

    today = date.today().isoformat()
    from resume_matcher import score_job_against_resume

    match_score, breakdown = score_job_against_resume(
        title=title,
        description=plain,
        tags=tags,
        relocate=relocate or "",
    )
    matched = breakdown.get("primary_skills", []) + breakdown.get("secondary_skills", [])
    job = {
        "company": company.strip(),
        "title": title.strip(),
        "url": url,
        "apply_url": apply_url,
        "status": "To Apply",
        "date_found": today,
        "match_score": match_score,
        "match_breakdown": {
            "primary": breakdown.get("primary_skills", []),
            "secondary": breakdown.get("secondary_skills", []),
            "role_match": breakdown.get("role_match", []),
        },
        "relocate": relocate or "",
        "remote": bool(remote) if remote is not None else None,
        "notes": f"Found via {SKILL_NAME} ({source}). Resume match: {', '.join(matched[:5]) or ', '.join(hits[:5])}.",
    }
    if country:
        job["country"] = country
    if location:
        job["location"] = location
    return job


def query_linkedin(keywords: str, country: str) -> list[dict]:
    from linkedin_jobs import fetch_linkedin

    pages_per_loc = 3 if country not in ("", "all") else 1
    return fetch_linkedin(
        country=country,
        keywords=keywords,
        max_pages_per_location=pages_per_loc,
        fetch_details=False,
    )


def query_arbeitnow(max_pages: int) -> list[dict]:
    results: list[dict] = []
    for visa_only in (True, False):
        pages = 5 if visa_only else max_pages
        for page in range(1, pages + 1):
            params: dict[str, str] = {"page": str(page)}
            if visa_only:
                params["visa_sponsorship"] = "true"
            url = "https://www.arbeitnow.com/api/job-board-api?" + urllib.parse.urlencode(params)
            try:
                payload = fetch_json(url)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                break
            jobs = payload.get("data", []) if isinstance(payload, dict) else []
            if not jobs:
                break
            for item in jobs:
                loc = item.get("location") or ""
                results.append(
                    {
                        "company": item.get("company_name", ""),
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "description": item.get("description", ""),
                        "tags": item.get("tags") or [],
                        "remote": item.get("remote"),
                        "source": "arbeitnow",
                        "slug": item.get("slug", ""),
                        "location": loc,
                        "country": loc.split(",")[-1].strip() if loc else "",
                    }
                )
            links = payload.get("links", {}) if isinstance(payload, dict) else {}
            if not links.get("next"):
                break
    return results


def query_remotive() -> list[dict]:
    url = "https://remotive.com/api/remote-jobs?category=software-dev"
    try:
        payload = fetch_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    results: list[dict] = []
    for item in payload.get("jobs", []):
        results.append(
            {
                "company": item.get("company_name", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "tags": item.get("tags") or [],
                "remote": True,
                "source": "remotive",
                "slug": str(item.get("id", "")),
            }
        )
    return results


def run_job_finder_skill(*, country: str = "all", max_arbeitnow_pages: int = 8) -> dict:
    """
    Execute job-finder skill workflow.

    Steps (SKILL.md):
      1. Read finder_state.json
      2. Read job_preferences.md + career_profile.md
      3. Query job boards (LinkedIn primary)
      4. Filter by preferences and red lines
      5. Deduplicate against job_applications.json
      6. Append new jobs with status To Apply
      7. Update finder_state.json
    """
    steps: dict[str, object] = {}

    # Step 1 — read state
    state = load_state()
    steps["1_read_state"] = {
        "last_linkedin_search_date": state.get("last_linkedin_search_date"),
        "last_job_board_checkpoint": state.get("last_job_board_checkpoint"),
        "search_mode": state.get("search_mode"),
    }

    # Step 2 — read preferences + profile
    prefs = parse_preferences()
    profile = parse_career_profile()
    keywords = prefs.get("tech_stack", [])
    red_lines = prefs.get("red_lines", [])
    target_roles = profile.get("target_roles", [])
    relocate_only = state.get("search_mode") == "relocate_visa_only"
    search_keywords = build_search_keywords(prefs, profile)
    steps["2_read_preferences"] = {
        "tech_stack": keywords,
        "red_lines": red_lines,
        "target_roles": target_roles,
        "work_type": prefs.get("work_type", []),
        "search_keywords": search_keywords,
        "relocate_only": relocate_only,
    }

    # Step 3 — query boards (LinkedIn first per skill)
    listings: list[dict] = []
    board_counts: dict[str, int] = {}
    try:
        linkedin = query_linkedin(search_keywords, country)
        board_counts["linkedin"] = len(linkedin)
        listings.extend(linkedin)
    except Exception as exc:
        board_counts["linkedin"] = 0
        steps["3_linkedin_error"] = str(exc)
    arbeitnow = query_arbeitnow(max_arbeitnow_pages)
    board_counts["arbeitnow"] = len(arbeitnow)
    listings.extend(arbeitnow)
    remotive = query_remotive()
    board_counts["remotive"] = len(remotive)
    listings.extend(remotive)
    steps["3_query_boards"] = board_counts

    # Step 5 prep — load existing for dedup
    existing = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    by_pair, by_url = existing_keys(existing)

    # Steps 4 + 5 + 6 — filter, dedupe, collect new
    scanned = 0
    skipped_redline = 0
    skipped_tech = 0
    skipped_relocate = 0
    skipped_duplicate = 0
    skipped_country = 0
    added: list[dict] = []
    last_checkpoint = state.get("last_job_board_checkpoint", "")
    seen_slugs: set[str] = set()

    for raw in listings:
        slug = f"{raw.get('source')}:{raw.get('slug') or raw.get('url')}"
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        scanned += 1

        plain = strip_html(raw.get("description", ""))
        blob = f"{raw['title']} {plain} {' '.join(raw.get('tags', []))}".lower()

        if red_line_from_preferences(blob, red_lines):
            skipped_redline += 1
            continue
        if not role_tech_hits(raw["title"], raw.get("tags", []), raw.get("description", ""), keywords, target_roles):
            skipped_tech += 1
            continue

        if raw.get("source") == "linkedin" and not plain:
            try:
                from linkedin_jobs import fetch_job_description

                plain = fetch_job_description(raw["slug"])
                raw["description"] = plain
                blob = f"{raw['title']} {plain} {' '.join(raw.get('tags', []))}".lower()
            except Exception:
                pass

        if relocate_only and not relocate_hint(blob):
            skipped_relocate += 1
            continue

        job_country = raw.get("country") or ""
        if country not in ("", "all") and job_country and job_country.lower() != country.lower():
            if country.lower() not in (raw.get("location") or "").lower():
                skipped_country += 1
                continue

        job = raw_to_job(
            company=raw["company"],
            title=raw["title"],
            url=raw["url"],
            description=raw.get("description", ""),
            tags=raw.get("tags", []),
            remote=raw.get("remote"),
            source=raw.get("source", "unknown"),
            keywords=keywords,
            target_roles=target_roles,
            red_lines=red_lines,
            relocate_only=relocate_only,
            country=job_country,
            location=raw.get("location", ""),
        )
        if not job:
            continue
        if is_duplicate(job, by_pair, by_url):
            skipped_duplicate += 1
            continue

        added.append(job)
        by_pair.add(normalize_key(job["company"], job["title"]))
        by_url.add(normalize_url(job["url"]))
        if job.get("apply_url"):
            by_url.add(normalize_url(job["apply_url"]))
        last_checkpoint = slug

    steps["4_filter"] = {
        "skipped_redline": skipped_redline,
        "skipped_tech": skipped_tech,
        "skipped_relocate": skipped_relocate,
        "skipped_country": skipped_country,
    }
    steps["5_deduplicate"] = {"skipped_duplicate": skipped_duplicate}

    if added:
        existing.extend(added)
        APPLICATIONS_PATH.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    steps["6_save"] = {"added": len(added), "path": str(APPLICATIONS_PATH)}

    # Step 7 — update state
    state["last_linkedin_search_date"] = date.today().isoformat()
    state["last_search_country"] = country
    if last_checkpoint:
        state["last_job_board_checkpoint"] = last_checkpoint
    save_state(state)
    steps["7_update_state"] = {
        "last_linkedin_search_date": state["last_linkedin_search_date"],
        "last_job_board_checkpoint": state.get("last_job_board_checkpoint"),
    }

    return {
        "ok": True,
        "skill": SKILL_NAME,
        "steps": steps,
        "scanned": scanned,
        "added": len(added),
        "skipped_duplicate": skipped_duplicate,
        "skipped_redline": skipped_redline,
        "skipped_tech": skipped_tech,
        "skipped_relocate": skipped_relocate,
        "skipped_country": skipped_country,
        "linkedin_scanned": board_counts.get("linkedin", 0),
        "search_country": country,
        "search_mode": state.get("search_mode", "default"),
        "new_jobs": [
            {
                "company": j["company"],
                "title": j["title"],
                "match_score": j["match_score"],
                "country": j.get("country", ""),
            }
            for j in added
        ],
    }


# Backward-compatible alias used by server
run_finder = run_job_finder_skill


def main() -> None:
    parser = argparse.ArgumentParser(description="Run job-finder skill")
    parser.add_argument("--country", "-c", default="all", help="LinkedIn search country (default: all)")
    parser.add_argument("--arbeitnow-pages", type=int, default=8)
    args = parser.parse_args()
    result = run_job_finder_skill(country=args.country, max_arbeitnow_pages=args.arbeitnow_pages)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
