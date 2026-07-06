"""LinkedIn guest API job search (no login required)."""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Full list for single-country search + list filter dropdown
ALL_COUNTRIES = [
    "Worldwide",
    "Remote",
    "European Union",
    "United States",
    "United Kingdom",
    "Germany",
    "Netherlands",
    "France",
    "Spain",
    "Portugal",
    "Canada",
    "Australia",
    "Ireland",
    "Switzerland",
    "Sweden",
    "Poland",
    "United Arab Emirates",
    "Singapore",
    "India",
    "Italy",
    "Austria",
    "Belgium",
    "Denmark",
    "Norway",
    "Finland",
    "Czech Republic",
    "Romania",
    "Hungary",
    "Turkey",
    "Japan",
    "South Korea",
    "Brazil",
    "Mexico",
    "Argentina",
    "South Africa",
    "Israel",
    "New Zealand",
    "Malaysia",
    "Thailand",
    "Vietnam",
    "Philippines",
    "Indonesia",
    "Egypt",
    "Nigeria",
    "Kenya",
    "Colombia",
    "Chile",
    "Ukraine",
    "Georgia",
    "Armenia",
]

# Subset scanned when "All countries" is selected (keeps search under ~2 min)
DEFAULT_LOCATIONS = ALL_COUNTRIES[:22]

COUNTRY_OPTIONS = [{"code": "all", "label": "All countries"}] + [
    {"code": loc, "label": loc} for loc in ALL_COUNTRIES
]


def _fetch_html(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _clean_text(text: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _parse_search_cards(html: str) -> list[dict]:
    cards: list[dict] = []
    for block in re.split(r"<li\b", html):
        if "data-entity-urn" not in block:
            continue
        job_id_m = re.search(r"data-entity-urn=\"urn:li:jobPosting:(\d+)\"", block)
        if not job_id_m:
            continue
        job_id = job_id_m.group(1)

        title_m = re.search(r"base-search-card__title[^>]*>\s*(.*?)\s*</h3>", block, re.S)
        company_m = re.search(r"base-search-card__subtitle.*?<a[^>]*>\s*(.*?)\s*</a>", block, re.S)
        location_m = re.search(r"job-search-card__location[^>]*>\s*(.*?)\s*</span>", block, re.S)
        link_m = re.search(r'href="(https?://[^"]+/jobs/view/[^"?]+)', block)

        title = _clean_text(title_m.group(1) if title_m else "")
        company = _clean_text(company_m.group(1) if company_m else "")
        location = _clean_text(location_m.group(1) if location_m else "")
        url = link_m.group(1) if link_m else f"https://www.linkedin.com/jobs/view/{job_id}"

        if not title:
            continue
        cards.append(
            {
                "job_id": job_id,
                "company": company,
                "title": title,
                "location": location,
                "url": url.split("?")[0],
            }
        )
    return cards


def _parse_country(location: str, search_location: str) -> str:
    if search_location and search_location not in ("all", "Worldwide", "Remote", "European Union"):
        return search_location
    if not location:
        return search_location or "Unknown"
    parts = [p.strip() for p in location.split(",") if p.strip()]
    return parts[-1] if parts else search_location or "Unknown"


def fetch_job_description(job_id: str) -> str:
    try:
        html = _fetch_html(DETAIL_URL.format(job_id=job_id))
    except (urllib.error.URLError, TimeoutError):
        return ""
    for pattern in (
        r'<div class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>',
        r'<div class="description__text[^"]*"[^>]*>(.*?)</div>',
    ):
        match = re.search(pattern, html, re.S)
        if match:
            return _clean_text(match.group(1))
    return ""


def search_location(
    *,
    location: str,
    keywords: str,
    max_pages: int = 2,
    fetch_details: bool = False,
    delay_s: float = 0.7,
) -> list[dict]:
    results: list[dict] = []
    seen_ids: set[str] = set()

    for page in range(max_pages):
        params = {
            "keywords": keywords,
            "location": location,
            "start": str(page * 25),
            "f_TPR": "r604800",  # past week
        }
        url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
        try:
            html = _fetch_html(url)
        except (urllib.error.URLError, TimeoutError):
            break

        cards = _parse_search_cards(html)
        if not cards:
            break

        for card in cards:
            if card["job_id"] in seen_ids:
                continue
            seen_ids.add(card["job_id"])

            description = ""
            if fetch_details:
                time.sleep(delay_s)
                description = fetch_job_description(card["job_id"])

            country = _parse_country(card["location"], location)
            results.append(
                {
                    "company": card["company"],
                    "title": card["title"],
                    "url": card["url"],
                    "description": description,
                    "tags": [],
                    "remote": location == "Remote" or "remote" in card["location"].lower(),
                    "source": "linkedin",
                    "slug": card["job_id"],
                    "location": card["location"],
                    "country": country,
                    "search_location": location,
                }
            )

        time.sleep(delay_s)

    return results


def fetch_linkedin(
    *,
    country: str = "all",
    keywords: str,
    max_pages_per_location: int = 2,
    fetch_details: bool = False,
) -> list[dict]:
    if country in ("", "all"):
        locations = DEFAULT_LOCATIONS
    elif country in ALL_COUNTRIES:
        locations = [country]
    else:
        locations = [country]
    all_results: list[dict] = []
    seen: set[str] = set()

    for location in locations:
        batch = search_location(
            location=location,
            keywords=keywords,
            max_pages=max_pages_per_location,
            fetch_details=fetch_details,
        )
        for item in batch:
            key = item["slug"]
            if key in seen:
                continue
            seen.add(key)
            all_results.append(item)

    return all_results
