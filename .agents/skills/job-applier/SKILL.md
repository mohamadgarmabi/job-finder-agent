---
name: job-applier
description: Tailor cover letters, autofill application forms, upload resume, pause for human approval on CAPTCHA or complex questions, and update job status to Applied. Use when applying to jobs, drafting cover letters, or processing entries with status "To Apply" in job_applications.json.
---

# Job Applier

Automate job applications with personalization and mandatory human checkpoints.

## Data Files

| File | Purpose |
|------|---------|
| `job_applications.json` | Queue and status tracking |
| `career_profile.md` | Experience, values, target roles |
| `resume.pdf` | Final resume — send as-is, never modify |
| `job_preferences.md` | Optional context for tone/fit |

## Workflow

Copy and track progress:

```
Task Progress:
- [ ] Pick job with status "To Apply"
- [ ] Analyze JD vs career_profile.md
- [ ] Draft personalized cover letter
- [ ] Open application form
- [ ] Autofill basic fields
- [ ] Upload resume.pdf
- [ ] Pause if CAPTCHA or complex questions
- [ ] Submit after user approval
- [ ] Update status to Applied
```

### Step 1: Select Job

From `job_applications.json`, pick the next entry where `status` is `"To Apply"`. Confirm with the user before proceeding.

### Step 2: Analyze Fit

Read the job description (from `url` or user-provided text). Compare against `career_profile.md`:

- `target_roles` — role alignment
- `experience_summary` — bullets to highlight
- `core_values` — tone and emphasis

Note 3–5 strongest matches and any gaps to address honestly (not invent experience).

### Step 3: Draft Cover Letter

Structure:

1. Opening — role + company, one sentence on fit
2. Body — 2 paragraphs mapping `experience_summary` to JD requirements
3. Closing — enthusiasm, availability, sign-off with name from profile

Save draft in the job entry's `notes` field before submission. Show the user the full letter for approval.

### Step 4: Autofill Basic Fields

Map from `career_profile.md` and user-provided contact info:

| Field | Source |
|-------|--------|
| Full name | `name` in career_profile |
| Email | user config / ask if missing |
| Phone | user config / ask if missing |
| LinkedIn / GitHub / Portfolio | user config / ask if missing |

Never guess missing PII. Ask the user.

### Step 5: Upload Resume

Attach `resume.pdf` exactly as stored. Do not edit, regenerate, or substitute another file unless the user explicitly provides one.

### Step 6: Human-in-the-Loop Pauses

**Stop and ask the user** when encountering:

- CAPTCHA or bot verification
- Multi-step identity verification
- Open-ended questions requiring personal judgment (e.g. "Why this company?", salary expectations, visa status)
- Legal attestations the user must confirm
- Any step that could submit without explicit approval

Present options clearly. Do not auto-submit past these gates.

### Step 7: Submit

Only submit after explicit user approval ("submit", "looks good", etc.).

### Step 8: Update Status

After successful submission, update the entry in `job_applications.json`:

```json
{
  "status": "Applied",
  "date_applied": "YYYY-MM-DD",
  "notes": "Custom cover letter sent highlighting [key themes]"
}
```

Preserve existing fields (`company`, `title`, `url`, `date_found`).

## Safety Rules

1. Never fabricate work history, skills, or credentials
2. Never bypass CAPTCHA or ToS restrictions
3. Never submit without user approval
4. Never modify `resume.pdf`
5. One application at a time unless user requests batch mode

## Output

Report to the user:

- Company and role applied to
- Cover letter summary (or full text if short)
- New status and `date_applied`
- Any jobs still in `To Apply` queue
