---
name: job-finder
description: Discover job listings, filter them by preferences and red lines, deduplicate against existing applications, and save matches to the local queue. Use when searching for jobs, running job discovery, updating finder_state, or populating job_applications.json with status "To Apply".
---

# Job Finder

Search job boards, filter results, and store new matches in the local JSON database.

## Automated runner (preferred)

The skill is implemented in `scripts/job_finder.py`. It runs all steps below automatically.

```bash
# CLI
python scripts/job_finder.py
python scripts/job_finder.py --country Germany

# UI
python scripts/server.py
# → click "Find new jobs" (runs POST /api/jobs/search)
```

Entry point in code: `run_job_finder_skill()` in `scripts/job_finder.py`.

## Data Files

| File | Purpose |
|------|---------|
| `finder_state.json` | Checkpoints: last search date, last board cursor |
| `job_preferences.md` | Tech stack, work type, red lines |
| `job_applications.json` | All known applications (dedup source) |
| `career_profile.md` | Context for relevance scoring (optional) |

## Workflow

Copy and track progress:

```
Task Progress:
- [ ] Read finder_state.json
- [ ] Read job_preferences.md
- [ ] Query job boards
- [ ] Filter by preferences and red lines
- [ ] Deduplicate against job_applications.json
- [ ] Append new jobs with status "To Apply"
- [ ] Update finder_state.json
```

### Step 1: Read State

Load `finder_state.json`:

```json
{
  "last_linkedin_search_date": "YYYY-MM-DD",
  "last_job_board_checkpoint": "id_or_cursor",
  "search_mode": "relocate_visa_only",
  "last_search_country": "all"
}
```

Use `last_linkedin_search_date` to avoid re-fetching stale listings. Use `last_job_board_checkpoint` to resume pagination.

### Step 2: Read Preferences

Parse `job_preferences.md` for:

- **tech_stack** — preferred technologies
- **work_type** — e.g. Remote, Hybrid, Relocate
- **red_lines** — hard exclusions (on-site, legacy stack, etc.)

Parse `career_profile.md` for:

- **target_roles** — used for keyword building and title matching

### Step 3: Query Job Boards

Search based on preferences. **Primary source: LinkedIn Jobs** (guest API via `scripts/linkedin_jobs.py`).

Secondary sources: Arbeitnow, Remotive.

Search parameters derived from preferences:

- Keywords: `tech_stack` + `search_keywords` + `target_roles` from `career_profile.md`
- Location: UI `--country` / `search_country` (all countries or one country)
- Date posted: LinkedIn `f_TPR=r604800` (past week)

If automation fails, ask the user to paste listings, then continue from Step 4.

### Step 4: Filter

**Include** when:

- Role aligns with `tech_stack` and `target_roles`
- Work arrangement matches `work_type`
- If `search_mode` is `relocate_visa_only`, listing must mention visa/relocation

**Score** each match with `scripts/resume_matcher.py` against `resume_profile.json` (from `Mohammad Garmabi Senior Software Engineer.pdf`):

- Primary skills (React, Next.js, TypeScript): up to 40 pts
- Secondary skills (Redux, Nx, Vitest, etc.): up to 20 pts
- Role title fit: up to 15 pts
- Seniority (Senior/Staff/Lead): up to 10 pts
- Domain strengths (performance, micro-frontends, etc.): up to 10 pts
- Relocation/visa: up to 15 pts

Re-score all jobs: `python scripts/rescore_jobs.py`

**Exclude** when description or title contains red-line keywords from `job_preferences.md`:

- on-site / in-office (per red lines)
- PHP, legacy, jQuery (per red lines)
- Non-engineering roles (recruiter, copywriter, etc.)

### Step 5: Deduplicate

Load `job_applications.json`. Skip a listing if any entry matches on:

- Same `url`, or
- Same `company` + `title` (normalized, case-insensitive)

### Step 6: Save New Jobs

Append each new match:

```json
{
  "company": "Company Name",
  "title": "Role Title",
  "url": "https://...",
  "status": "To Apply",
  "date_found": "YYYY-MM-DD",
  "country": "Germany",
  "match_score": 45,
  "notes": "Found via job-finder (linkedin). Tech: react, typescript."
}
```

Write atomically: read full array → append → write full array.

### Step 7: Update State

Set in `finder_state.json`:

- `last_linkedin_search_date` → today's date
- `last_job_board_checkpoint` → last processed listing id/cursor
- `last_search_country` → country used in search

## Output

Report to the user:

- Skill name and steps completed
- Count of jobs scanned, filtered, and added
- Count skipped (duplicate / red line / tech / relocate)
- Path to updated `job_applications.json`

## Status Values

| Status | Meaning |
|--------|---------|
| `To Apply` | New match, ready for job-applier |
| `Applied` | Submitted |
| `Rejected` | User or employer declined |
| `Interview` | In interview process |
