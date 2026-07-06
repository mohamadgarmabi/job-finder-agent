#!/usr/bin/env python3
"""Open job application URL, autofill from job_applications.json, never submit."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPLICATIONS_PATH = ROOT / "job_applications.json"

# Never click these — fill-only mode
SUBMIT_PATTERN = re.compile(
    r"submit|apply\s*now|send\s*application|complete\s*application|"
    r"confirm\s*application|finish|place\s*application",
    re.I,
)

FIELD_HINTS: dict[str, list[str]] = {
    "name": ["name", "full name", "first name", "last name", "candidate"],
    "email": ["email", "e-mail"],
    "phone": ["phone", "mobile", "tel", "telephone"],
    "linkedin": ["linkedin"],
    "github": ["github", "git hub"],
    "location": ["location", "city", "country", "where are you", "based in"],
    "cover_letter": [
        "cover letter",
        "cover note",
        "message",
        "motivation",
        "why",
        "additional",
        "comments",
        "tell us",
        "introduction",
    ],
    "salary": ["salary", "compensation", "expected pay", "rate", "hourly"],
    "english": ["english", "language level", "language proficiency"],
}


def load_job(company: str | None) -> dict:
    jobs = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    return _pick_job(jobs, company)


def load_job_by_company(company: str) -> dict:
    jobs = json.loads(APPLICATIONS_PATH.read_text(encoding="utf-8"))
    matches = [j for j in jobs if company.lower() in j.get("company", "").lower()]
    if not matches:
        print(f"No job matching company '{company}'.", file=sys.stderr)
        sys.exit(1)
    return matches[0]


def _pick_job(jobs: list[dict], company: str | None) -> dict:
    to_apply = [j for j in jobs if j.get("status") == "To Apply"]
    if not to_apply:
        print("No jobs with status 'To Apply'.", file=sys.stderr)
        sys.exit(1)

    if company:
        matches = [j for j in to_apply if company.lower() in j.get("company", "").lower()]
        if not matches:
            print(f"No 'To Apply' job matching company '{company}'.", file=sys.stderr)
            sys.exit(1)
        return matches[0]

    ready = [j for j in to_apply if j.get("autofill") and j.get("cover_letter_draft")]
    return ready[0] if ready else to_apply[0]


def collect_values(job: dict) -> dict[str, str]:
    autofill = job.get("autofill") or {}
    answers = job.get("application_answers") or {}
    values: dict[str, str] = {
        "name": autofill.get("name", ""),
        "email": autofill.get("email", ""),
        "phone": autofill.get("phone", ""),
        "linkedin": autofill.get("linkedin", ""),
        "github": autofill.get("github", ""),
        "location": autofill.get("location") or job.get("location", ""),
        "cover_letter": job.get("cover_letter_draft", ""),
        "salary": answers.get("salary_expectation", ""),
        "english": answers.get("english_level", ""),
    }
    for key, val in answers.items():
        if val and key not in values:
            values[key] = val
    return {k: v for k, v in values.items() if v}


def label_text(el) -> str:
    try:
        aria = el.get_attribute("aria-label") or ""
        placeholder = el.get_attribute("placeholder") or ""
        name = el.get_attribute("name") or ""
        el_id = el.get_attribute("id") or ""
        label = ""
        if el_id:
            lbl = el.page.locator(f'label[for="{el_id}"]').first
            if lbl.count():
                label = lbl.inner_text(timeout=500)
        return " ".join([label, aria, placeholder, name, el_id]).lower()
    except Exception:
        return ""


def match_field(label: str) -> str | None:
    for field, hints in FIELD_HINTS.items():
        if any(h in label for h in hints):
            return field
    return None


def fill_text_input(page, el, value: str) -> bool:
    try:
        tag = el.evaluate("e => e.tagName.toLowerCase()")
        input_type = (el.get_attribute("type") or "text").lower()
        if input_type in ("hidden", "submit", "button", "file", "checkbox", "radio"):
            return False
        if tag == "select":
            for opt in el.locator("option").all():
                text = (opt.inner_text() or "").lower()
                if value.lower() in text or text in value.lower():
                    opt.click()
                    return True
            return False
        if not el.is_visible():
            return False
        el.click(timeout=2000)
        el.fill(value)
        return True
    except Exception:
        return False


def try_click_apply(page) -> None:
    apply_selectors = [
        "text=/apply for this job/i",
        "text=/apply now/i",
        "a:has-text('Apply')",
        "button:has-text('Apply')",
        "[data-testid*='apply']",
    ]
    for sel in apply_selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=3000)
                page.wait_for_timeout(1500)
                return
        except Exception:
            continue


def upload_resume(page, resume_path: Path) -> bool:
    if not resume_path.is_file():
        print(f"Resume not found: {resume_path} — skip upload.")
        return False
    try:
        inputs = page.locator('input[type="file"]')
        count = inputs.count()
        for i in range(count):
            inp = inputs.nth(i)
            if inp.is_visible() or True:
                inp.set_input_files(str(resume_path))
                print(f"Uploaded resume: {resume_path.name}")
                return True
    except Exception as exc:
        print(f"Resume upload failed: {exc}")
    return False


def discover_ashby_application_url(apply_url: str) -> str | None:
    """Headless probe to resolve embedded Ashby application URL."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(apply_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
            for frame in page.frames:
                u = frame.url or ""
                if "ashbyhq.com" in u and "application" in u:
                    return u.split("?")[0]
            try_click_apply(page)
            page.wait_for_timeout(3000)
            for frame in page.frames:
                u = frame.url or ""
                if "ashbyhq.com" in u and "application" in u:
                    return u.split("?")[0]
        except Exception:
            return None
        finally:
            browser.close()
    return None


def resolve_form_url(apply_url: str) -> str:
    if "ashbyhq.com" in apply_url and "application" in apply_url:
        return apply_url
    ashby = discover_ashby_application_url(apply_url)
    if ashby:
        print(f"Resolved Ashby form: {ashby[:80]}...")
        return ashby
    return apply_url


def get_form_page(page):
    """Return page containing the application form (navigation already done)."""
    page.wait_for_timeout(1500)
    return page


def ashby_field(form, label_substr: str):
    """Locate Ashby field entry container by label text."""
    label = form.locator("label.ashby-application-form-question-title").filter(
        has_text=re.compile(label_substr, re.I)
    ).first
    if not label.count():
        return None, None
    entry = label.locator("xpath=ancestor::*[contains(@class,'ashby-application-form-field-entry')][1]")
    field_id = label.get_attribute("for")
    return entry, field_id


def fill_by_label(form, label_substr: str, value: str) -> bool:
    try:
        entry, field_id = ashby_field(form, label_substr)
        if not entry:
            return False
        if field_id:
            el = form.locator(f'[id="{field_id}"]')
            if el.count():
                el.scroll_into_view_if_needed()
                el.fill(value)
                return True
        inp = entry.locator("input[type='text'], input[type='email'], textarea").first
        if inp.count():
            inp.scroll_into_view_if_needed()
            inp.fill(value)
            return True
    except Exception:
        pass
    return False


def fill_ashby_combobox(form, label_substr: str, value: str) -> bool:
    try:
        entry, field_id = ashby_field(form, label_substr)
        if not entry:
            return False
        inp = entry.locator("input[aria-autocomplete='list'], input[placeholder*='typing']").first
        if not inp.count() and field_id:
            inp = form.locator(f'[id="{field_id}"]')
        if not inp.count():
            return False
        inp.scroll_into_view_if_needed()
        inp.click()
        inp.fill(value)
        form.wait_for_timeout(1000)
        option = form.locator("[role='option']").filter(has_text=re.compile(value.split(",")[0].split()[0], re.I)).first
        if option.count():
            option.click()
        else:
            form.keyboard.press("ArrowDown")
            form.keyboard.press("Enter")
        return True
    except Exception:
        return False


def click_ashby_yes_no(form, question_substr: str, answer_yes: bool = True) -> bool:
    try:
        entry, _ = ashby_field(form, question_substr)
        if not entry:
            return False
        btn_text = "Yes" if answer_yes else "No"
        btn = entry.locator("button").filter(has_text=re.compile(f"^{btn_text}$", re.I)).first
        if btn.count() and btn.is_visible():
            btn.scroll_into_view_if_needed()
            btn.click()
            return True
    except Exception:
        pass
    return False


def fill_ashby(form, values: dict[str, str], resume_path: Path, job: dict) -> None:
    answers = job.get("application_answers") or {}

    def log(field: str, ok: bool, preview: str = "") -> None:
        if ok:
            print(f"Filled [{field}]: {preview[:70]}{'...' if len(preview) > 70 else ''}")

    if form.locator("#_systemfield_name").count():
        v = values.get("name", "")
        form.locator("#_systemfield_name").fill(v)
        log("name", bool(v), v)

    if form.locator("#_systemfield_email").count():
        v = values.get("email", "")
        form.locator("#_systemfield_email").fill(v)
        log("email", bool(v), v)

    if resume_path.is_file() and form.locator("#_systemfield_resume").count():
        form.locator("#_systemfield_resume").set_input_files(str(resume_path))
        print(f"Uploaded resume: {resume_path.name}")
    elif not resume_path.is_file():
        print(f"Resume not found: {resume_path} — skip upload.")

    v = values.get("linkedin", "")
    if fill_by_label(form, "linkedin", v):
        log("linkedin", bool(v), v)

    loc = values.get("location", "Iran")
    if fill_ashby_combobox(form, "current location", loc):
        log("location", True, loc)

    est = answers.get("est_overlap", "")
    if est and click_ashby_yes_no(form, "overlap with Eastern", answer_yes=est.lower().startswith("yes")):
        log("est_overlap", True, "Yes" if est.lower().startswith("yes") else "No")

    weekend = answers.get("weekend_work", "yes")
    if click_ashby_yes_no(form, "work hard", answer_yes=str(weekend).lower().startswith("yes")):
        log("weekend_work", True, "Yes")

    eng = values.get("english", answers.get("english_level", ""))
    if fill_by_label(form, "english", eng):
        log("english", bool(eng), eng)

    proud = answers.get(
        "proud_project",
        "Migrating a large React product to an Nx monorepo with micro-frontends — ~25% load-time improvement and Lighthouse 100 on key surfaces while the team kept shipping features.",
    )
    if fill_by_label(form, "most proud", proud):
        log("proud_project", True, proud)

    gh = values.get("github", "")
    if fill_by_label(form, "github", gh):
        log("github", bool(gh), gh)

    why = answers.get("why_dualentry", answers.get("why_interested", ""))
    if why and fill_by_label(form, "why", why):
        log("why_dualentry", True, why)


def fill_generic_form(form, values: dict[str, str], resume_path: Path) -> None:
    filled: set[str] = set()
    fields = form.locator("input, textarea, select")
    count = fields.count()

    for i in range(count):
        el = fields.nth(i)
        label = label_text(el)
        if not label.strip():
            continue
        field = match_field(label)
        if not field or field in filled:
            for key, val in values.items():
                if key in filled or key in FIELD_HINTS:
                    continue
                if key.replace("_", " ") in label or key.replace("_", "-") in label:
                    if fill_text_input(form, el, val):
                        filled.add(key)
                        print(f"Filled [{key}]: {val[:60]}...")
                    break
            continue
        val = values.get(field, "")
        if not val:
            continue
        if fill_text_input(form, el, val):
            filled.add(field)
            preview = val[:60] + ("..." if len(val) > 60 else "")
            print(f"Filled [{field}]: {preview}")

    if "cover_letter" not in filled and values.get("cover_letter"):
        for ta in form.locator("textarea").all():
            try:
                if ta.is_visible() and not (ta.input_value() or "").strip():
                    ta.fill(values["cover_letter"])
                    filled.add("cover_letter")
                    print("Filled [cover_letter] in empty textarea")
                    break
            except Exception:
                continue

    upload_resume(form, resume_path)

    for key, val in values.items():
        if key in filled or key in ("name", "email", "phone", "linkedin", "github", "location", "cover_letter"):
            continue
        for ta in form.locator("textarea, input[type='text']").all():
            try:
                if ta.is_visible() and not (ta.input_value() or "").strip():
                    hint = label_text(ta)
                    if any(w in hint for w in key.replace("_", " ").split()):
                        if fill_text_input(form, ta, val):
                            filled.add(key)
                            print(f"Filled [{key}] (heuristic)")
                            break
            except Exception:
                continue


def fill_form(page, values: dict[str, str], resume_path: Path, job: dict) -> None:
    form = get_form_page(page)
    if "ashbyhq.com" in page.url:
        fill_ashby(form, values, resume_path, job)
    else:
        fill_generic_form(form, values, resume_path)


def block_submit_clicks(page) -> None:
    """Abort clicks on submit-like buttons (safety net)."""

    page.add_init_script(
        """
        document.addEventListener('click', (e) => {
          const t = e.target.closest('button, input[type=submit], a');
          if (!t) return;
          const text = (t.innerText || t.value || '').toLowerCase();
          if (/submit|apply now|send application|complete application|confirm application/.test(text)) {
            e.preventDefault();
            e.stopPropagation();
            console.warn('[fill_application] Blocked submit click:', text);
          }
        }, true);
        """
    )


def run(job: dict, headless: bool, keep_open: bool, detach: bool = False) -> None:
    from playwright.sync_api import sync_playwright

    url = job.get("apply_url") or job.get("url")
    if not url:
        print("Job has no apply_url or url.", file=sys.stderr)
        sys.exit(1)

    form_url = resolve_form_url(url)
    values = collect_values(job)
    autofill = job.get("autofill") or {}
    resume_name = autofill.get("resume", "resume.pdf")
    resume_path = ROOT / resume_name

    print(f"\n{'=' * 60}")
    print(f"Company : {job.get('company')}")
    print(f"Role    : {job.get('title')}")
    print(f"URL     : {form_url}")
    print(f"Mode    : FILL ONLY — will NOT submit")
    print(f"{'=' * 60}\n")

    with sync_playwright() as p:
        launch_opts: dict = {"headless": headless, "slow_mo": 80}
        if not headless:
            launch_opts["args"] = ["--start-maximized"]
        browser = None
        for attempt in ("bundled", "chrome"):
            try:
                if attempt == "chrome":
                    browser = p.chromium.launch(channel="chrome", **launch_opts)
                else:
                    browser = p.chromium.launch(**launch_opts)
                break
            except Exception as exc:
                if attempt == "chrome":
                    print(f"Browser launch failed: {exc}", file=sys.stderr)
                    sys.exit(1)
        context = browser.new_context(viewport=None if not headless else {"width": 1280, "height": 900})
        page = context.new_page()
        block_submit_clicks(page)

        page.goto(form_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        fill_form(page, values, resume_path, job)

        print("\n✓ Form filled. Browser left open — review and submit yourself.")
        if detach:
            print("  Detached mode — browser stays open. Close it when done reviewing.\n")
            try:
                page.wait_for_timeout(86_400_000)
            except Exception:
                pass
        elif keep_open:
            print("  Press Enter here to close the browser.\n")
            try:
                input()
            except EOFError:
                page.wait_for_timeout(300_000)

        if not detach:
            context.close()
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Autofill job application (no submit)")
    parser.add_argument("--company", "-c", help="Company name substring to match")
    parser.add_argument("--headless", action="store_true", help="Run headless (default: visible browser)")
    parser.add_argument("--no-wait", action="store_true", help="Close browser immediately after fill")
    parser.add_argument("--detach", action="store_true", help="Keep browser open without stdin (for UI server)")
    args = parser.parse_args()

    if args.company:
        job = load_job_by_company(args.company)
    else:
        job = load_job(None)
    run(
        job,
        headless=args.headless,
        keep_open=not args.no_wait and not args.detach,
        detach=args.detach,
    )


if __name__ == "__main__":
    main()
