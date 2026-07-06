# job-finder-agent

## UI — Job Applications

```bash
source .venv/bin/activate
python scripts/server.py
```

Open: http://127.0.0.1:8765

## job-finder skill

Job discovery follows `.agents/skills/job-finder/SKILL.md` via `scripts/job_finder.py`:

```bash
python scripts/job_finder.py
python scripts/job_finder.py --country Germany
```

- **Find new jobs** (UI) → runs `run_job_finder_skill()` (LinkedIn + Arbeitnow + Remotive)
- **Open & fill** → Playwright autofills the form (does not submit)
- **Mark applied** → sets status to `Applied`
- Filter by status, country, date, company/role
