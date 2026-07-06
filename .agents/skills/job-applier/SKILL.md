---
name: job-applier
description: Tailor cover letters, open application forms in browser, autofill all fields, upload resume, pause for human review — never auto-submit. Use when applying to jobs, drafting cover letters, or processing entries with status "To Apply" in job_applications.json.
---

# Job Applier

Automate job application prep with browser autofill. **Fill everything, never submit.**

## Data Files

| File | Purpose |
|------|---------|
| `job_applications.json` | Queue and status tracking |
| `career_profile.md` | Experience, values, target roles |
| `resume.pdf` | Final resume — send as-is, never modify |
| `job_preferences.md` | Optional context for tone/fit |
| `scripts/fill_application.py` | Browser autofill runner (Playwright) |

## Default Mode: Fill Only (No Submit)

The agent **must open the apply URL and autofill the form**, then **stop before submit**. The user reviews in the browser and clicks Submit themselves.

```
Task Progress:
- [ ] Pick job with status "To Apply"
- [ ] Ensure autofill package exists (cover_letter_draft, application_answers, autofill)
- [ ] Run browser autofill script
- [ ] Pause for user review (CAPTCHA, attestations, final check)
- [ ] User submits manually
- [ ] Update status to Applied only after user confirms submission
```

### Browser Autofill (required)

From project root, run:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # or uses system Chrome as fallback
python scripts/fill_application.py              # next ready "To Apply" job
python scripts/fill_application.py -c DualEntry   # specific company
python scripts/fill_application.py -c DualEntry --detach  # keep browser open, no terminal wait
```

Behavior:

1. Opens `apply_url` in a **visible** Chromium window
2. Clicks "Apply" if needed
3. Fills name, email, phone, LinkedIn, GitHub, location, cover letter, salary, and `application_answers`
4. Uploads `resume.pdf` when a file input is found
5. **Blocks submit-button clicks** as a safety net
6. Leaves browser open until user presses Enter in terminal

If Playwright is unavailable, fall back to `open "<apply_url>"` plus a paste cheat sheet — still **never submit**.

### Step 1: Select Job

From `job_applications.json`, pick the next entry where `status` is `"To Apply"`. Prefer jobs with a complete autofill package (`autofill`, `cover_letter_draft`, `application_answers`).

### Step 2: Prepare Package (if missing)

Read the job description (from `url` or user-provided text). Compare against `career_profile.md`. Draft cover letter and answers; save to the job entry before running autofill.

Cover letter structure:

1. Opening — role + company, one sentence on fit
2. Body — 2 paragraphs mapping `experience_summary` to JD requirements
3. Closing — enthusiasm, availability, sign-off with name from profile

### Step 3: Autofill Fields

Map from job entry and `career_profile.md`:

| Field | Source |
|-------|--------|
| Full name | `autofill.name` or `name` in career_profile |
| Email | `autofill.email` |
| Phone | `autofill.phone` |
| LinkedIn / GitHub | `autofill.linkedin`, `autofill.github` |
| Cover letter | `cover_letter_draft` |
| Custom questions | `application_answers` |

Never guess missing PII. Ask the user.

### Step 4: Upload Resume

Attach `resume.pdf` exactly as stored. Do not edit, regenerate, or substitute unless the user explicitly provides one.

### Step 5: Human Review (mandatory before submit)

**Stop and tell the user** to review in the browser when:

- CAPTCHA or bot verification appears
- Multi-step identity verification is required
- Legal attestations need confirmation
- Any field looks wrong or empty

Present: company, role, URL, what was filled, what may need manual fix.

### Step 6: Submit — User Only

**Never auto-submit.** Only update status after the user explicitly confirms they submitted ("submitted", "done", etc.).

### Step 7: Update Status

After user confirms submission:

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
3. **Never submit without explicit user action in the browser**
4. Never modify `resume.pdf`
5. One application at a time unless user requests batch mode

## Output

Report to the user:

- Company and role
- Apply URL opened
- Fields filled / resume uploaded / gaps needing manual input
- Reminder: review in browser, submit yourself, then confirm so status can update
- Any jobs still in `To Apply` queue
