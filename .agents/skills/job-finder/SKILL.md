---
name: job-finder
description: Discover job listings, filter them by preferences and red lines, deduplicate against existing applications, and save matches to the local queue. Use when searching for jobs, running job discovery, updating finder_state, or populating job_applications.json with status "To Apply".
---

# Job Finder

Search job boards, filter results, and store new matches in the local JSON database.

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
  "last_job_board_checkpoint": "id_or_cursor"
}
```

Use `last_linkedin_search_date` to avoid re-fetching stale listings. Use `last_job_board_checkpoint` to resume pagination.

### Step 2: Read Preferences

Parse `job_preferences.md` for:

- **tech_stack** — preferred technologies
- **work_type** — e.g. Remote, Hybrid
- **red_lines** — hard exclusions (on-site, legacy stack, etc.)

### Step 3: Query Job Boards

Search based on preferences. Primary source: LinkedIn Jobs.

Search parameters to derive from preferences:

- Keywords: join `tech_stack` + `target_roles` from `career_profile.md`
- Location / remote filter: match `work_type`
- Date posted: since `last_linkedin_search_date` when possible

If browser automation is unavailable, ask the user to paste listings or export results, then continue from Step 4.

### Step 4: Filter

**Include** when:

- Role aligns with `tech_stack` and `target_roles`
- Work arrangement matches `work_type`

**Exclude** when description or title contains red-line keywords (case-insensitive), e.g.:

- "on-site", "onsite", "in-office" (if remote-only)
- "jQuery", "PHP", "legacy" (per user red lines)
- Any phrase listed under `red_lines` in `job_preferences.md`

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
  "notes": ""
}
```

Write atomically: read full array → append → write full array.

### Step 7: Update State

Set in `finder_state.json`:

- `last_linkedin_search_date` → today's date
- `last_job_board_checkpoint` → last processed listing id/cursor

## Output

Report to the user:

- Count of jobs found, filtered, and added
- Count skipped (duplicate / red line)
- Path to updated `job_applications.json`

## Status Values

| Status | Meaning |
|--------|---------|
| `To Apply` | New match, ready for job-applier |
| `Applied` | Submitted |
| `Rejected` | User or employer declined |
| `Interview` | In interview process |
