"""Score job listings against resume_profile.json (extracted from resume PDF)."""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "resume_profile.json"
RESUME_PDF = ROOT / "Mohammad Garmabi Senior Software Engineer.pdf"


def strip_html(text: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def load_resume_profile() -> dict:
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return build_profile_from_pdf()


def save_resume_profile(profile: dict) -> None:
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_skills_from_text(text: str) -> tuple[list[str], list[str]]:
    lower = text.lower()
    primary = []
    secondary = []
    primary_candidates = [
        "react.js",
        "react",
        "next.js",
        "nextjs",
        "typescript",
        "javascript",
        "frontend",
        "front-end",
    ]
    secondary_candidates = [
        "remix",
        "solid.js",
        "node.js",
        "nestjs",
        "python",
        "django",
        "redux",
        "tanstack query",
        "react query",
        "zustand",
        "tailwind",
        "material ui",
        "mui",
        "micro-frontend",
        "monorepo",
        "nx",
        "vitest",
        "playwright",
        "docker",
        "fullstack",
        "full-stack",
    ]
    for skill in primary_candidates:
        if skill in lower and skill not in primary:
            primary.append(skill)
    for skill in secondary_candidates:
        if skill in lower and skill not in secondary:
            secondary.append(skill)
    return primary, secondary


def build_profile_from_pdf(pdf_path: Path | None = None) -> dict:
    path = pdf_path or RESUME_PDF
    if not path.exists():
        raise FileNotFoundError(f"Resume PDF not found: {path}")

    from pypdf import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    primary, secondary = _extract_skills_from_text(text)

    profile = {
        "source_pdf": path.name,
        "name": "Mohammad Garmabi",
        "headline": "Senior Software Engineer",
        "years_experience": 6,
        "primary_skills": primary or ["react", "next.js", "typescript", "javascript", "frontend"],
        "secondary_skills": secondary,
        "strengths": [
            "performance",
            "lighthouse",
            "micro-frontend",
            "monorepo",
            "design system",
            "ssr",
            "mentoring",
            "architecture",
            "ai-assisted",
            "payment",
            "api",
        ],
        "target_roles": [
            "frontend developer",
            "frontend engineer",
            "react engineer",
            "react developer",
            "senior frontend",
            "senior software engineer",
            "software engineer",
            "full stack engineer",
            "fullstack engineer",
            "staff frontend",
        ],
        "seniority": ["senior", "staff", "lead", "principal"],
        "avoid_seniority": ["junior", "intern", "internship", "entry level", "graduate"],
    }
    save_resume_profile(profile)
    return profile


def _hits(blob: str, terms: list[str]) -> list[str]:
    found: list[str] = []
    for term in terms:
        t = term.lower().strip()
        if t and t in blob and t not in found:
            found.append(t)
    return found


def score_job_against_resume(
    *,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    relocate: str | bool = "",
) -> tuple[int, dict]:
    """Return (match_score 0-100, breakdown dict)."""
    profile = load_resume_profile()
    plain = strip_html(description)
    blob = f"{title} {plain} {' '.join(tags or [])}".lower()
    title_l = title.lower()

    primary_hits = _hits(blob, profile.get("primary_skills", []))
    secondary_hits = _hits(blob, profile.get("secondary_skills", []))
    strength_hits = _hits(blob, profile.get("strengths", []))
    role_hits = _hits(title_l, profile.get("target_roles", []))

    score = 0
    breakdown: dict[str, object] = {
        "primary_skills": primary_hits,
        "secondary_skills": secondary_hits,
        "strengths": strength_hits,
        "role_match": role_hits,
    }

    # Primary stack match (max 40)
    score += min(len(primary_hits) * 10, 40)

    # Secondary / adjacent stack (max 20)
    score += min(len(secondary_hits) * 5, 20)

    # Role title fit (max 15)
    if role_hits:
        score += 15
    elif re.search(r"\b(developer|engineer|frontend|software)\b", title_l):
        score += 8

    # Seniority fit (max 10, penalty for junior)
    if any(s in title_l for s in profile.get("seniority", [])):
        score += 10
    if any(s in title_l for s in profile.get("avoid_seniority", [])):
        score -= 20

    # Domain strengths (max 10)
    score += min(len(strength_hits) * 4, 10)

    # Relocation / visa path (max 15)
    has_relocate = bool(relocate) or _hits(
        blob,
        ["visa sponsorship", "relocation", "relocate", "relocation package"],
    )
    if has_relocate:
        score += 15
        breakdown["relocate"] = True

    final = max(0, min(100, score))
    breakdown["total"] = final
    return final, breakdown


def score_job_record(job: dict) -> tuple[int, dict]:
    return score_job_against_resume(
        title=job.get("title", ""),
        description=job.get("cover_letter_draft", "") + " " + job.get("notes", ""),
        tags=[],
        relocate=job.get("relocate", ""),
    )


def rescore_all_jobs(jobs: list[dict]) -> list[dict]:
    for job in jobs:
        desc = ""
        if job.get("url", "").startswith("http"):
            desc = job.get("notes", "")
        score, breakdown = score_job_against_resume(
            title=job.get("title", ""),
            description=desc,
            tags=[],
            relocate=job.get("relocate", ""),
        )
        job["match_score"] = score
        job["match_breakdown"] = {
            "primary": breakdown.get("primary_skills", []),
            "secondary": breakdown.get("secondary_skills", []),
            "role_match": breakdown.get("role_match", []),
        }
    return jobs
