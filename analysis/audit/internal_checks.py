import re
from collections import Counter

from fetch_data import get_author_dirs, load_json

PROFILE_URLS = {
    "google_scholar": r"scholar\.google\.[^/]+/citations\?.*user=",
    "linkedin": r"linkedin\.com/in/",
    "researchgate": r"researchgate\.net/profile/"
}

# Check MathML first so it is not double-counted as HTML
MARKUP_PATTERNS = {
    "mml": re.compile(r"mml:", re.I),
    "html": re.compile(r"</?[a-z][^>]*>", re.I),
}


def get_profile_urls(author):
    profile_urls = {}

    for row in author["broad_impact"]:
        url = row.get("url")

        if not url:
            continue

        for profile_type, pattern in PROFILE_URLS.items():
            if re.search(pattern, url, re.I):
                profile_urls.setdefault(profile_type, url)
                break

    return profile_urls


def compare_profile_verifications(authors):
    comparisons = {}

    for author_id, author in authors.items():
        verification = author["profile"].get("verification") or {}
        profile_urls = get_profile_urls(author)
        profile_comparisons = {}

        for profile_type in PROFILE_URLS:
            url = profile_urls.get(profile_type)
            stored = verification.get(profile_type)

            if stored is None:
                verification_status = "missing"
            elif stored.get("verified"):
                verification_status = "verified"
            else:
                verification_status = "unverified"

            profile_comparisons[profile_type] = {
                "verification_status": verification_status,
                "url": url,
                "reason": stored.get("reason") if isinstance(stored, dict) else None,
            }

        comparisons[author_id] = profile_comparisons

    return comparisons


def compare_publication_counts(authors):
    comparisons = []

    for author_id, author in authors.items():
        claim = author["profile"].get("metrics", {}).get("publications")
        present = len(author["publications"])

        comparisons.append({
            "author_id": author_id,
            "claim": claim,
            "present": present,
        })

    return comparisons


def get_profiles_with_long_year_spans(authors):
    max_year_span = 100
    profiles = []

    for author_id, author in authors.items():
        years = [
            entry["year"]
            for entry in author["profile"].get("counts_by_year") or []
            if entry.get("works_count", 0) > 0 and entry.get("year") is not None
        ]

        if not years:
            continue

        earliest_year = min(years)
        latest_year = max(years)
        year_span = latest_year - earliest_year

        if year_span > max_year_span:
            profiles.append({
                "author_id": author_id,
                "earliest_year": earliest_year,
                "latest_year": latest_year,
                "year_span": year_span,
            })

    return profiles


def compare_deep_verifications(authors):
    comparisons = Counter()

    for author in authors.values():
        for publication in author["publications"]:
            deep_verification = publication.get("deep_verification")

            if not isinstance(deep_verification, dict):
                comparisons["deep_verification_absent"] += 1
                continue

            is_open_access = deep_verification.get("openAccessPdf") is not None

            if deep_verification.get("verified"):
                bucket = "verified_with_pdf" if is_open_access else "verified_without_pdf"
            elif is_open_access:
                bucket = "unverified_with_pdf"
            else:
                bucket = "unverified_empty"

            comparisons[bucket] += 1

            if not deep_verification.get("verified") and (
                deep_verification.get("s2_url") or deep_verification.get("openAccessPdf")
            ):
                comparisons["unverified_but_carries_a_link"] += 1

    return dict(comparisons)


def load_author_records():
    authors = {}

    for author_dir in get_author_dirs():
        profile = load_json(author_dir, "profile.json")
        publications = load_json(author_dir, "publications.json")

        try:
            broad_impact = load_json(author_dir, "broad_impact.json")
        except FileNotFoundError:
            broad_impact = []

        authors[profile["id"]] = {
            "profile": profile,
            "publications": publications,
            "broad_impact": broad_impact,
        }

    return authors

def get_titles_with_markup(authors):
    titles_by_markup = {markup_type: [] for markup_type in MARKUP_PATTERNS}

    for author_id, author in authors.items():
        for publication in author["publications"]:
            title = publication.get("title", "")

            for markup_type, pattern in MARKUP_PATTERNS.items():
                if pattern.search(title):
                    titles_by_markup[markup_type].append({
                        "author_id": author_id,
                        "title": title,
                    })
                    break

    return titles_by_markup
