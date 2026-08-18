import re
from collections import Counter

from comparison_utils import get_normalized_words
from fetch_data import get_author_dirs, load_json, normalize_doi

PROFILE_URLS = {
    "google_scholar": r"scholar\.google\.[^/]+/citations\?.*user=",
    "linkedin": r"linkedin\.com/in/",
    "researchgate": r"researchgate\.net/profile/",
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


def compare_profile_verifications(internal_data):
    comparisons = []

    for author_id, author in internal_data.items():
        verification = author["profile"].get("verification") or {}
        profile_urls = get_profile_urls(author)
        for profile_type in PROFILE_URLS:
            url = profile_urls.get(profile_type)
            stored = verification.get(profile_type)

            if stored is None:
                verification_status = "missing"
            elif stored.get("verified"):
                verification_status = "verified"
            else:
                verification_status = "unverified"

            comparisons.append(
                {
                    "author_id": author_id,
                    "source": profile_type,
                    "verification_status": verification_status,
                    "matching_profile_url": bool(url),
                    "reason": stored.get("reason") if isinstance(stored, dict) else None,
                }
            )

    return comparisons


def get_publication_claims(internal_data):
    claims = []

    for author_id, author in internal_data.items():
        claim = author["profile"].get("metrics", {}).get("publications")

        claims.append(
            {
                "author_id": author_id,
                "claim": claim,
            }
        )

    return claims


def get_year_span(counts_by_year):
    years = [
        entry["year"]
        for entry in counts_by_year or []
        if entry.get("works_count", 0) > 0 and entry.get("year") is not None
    ]

    if not years:
        return None

    earliest_year = min(years)
    latest_year = max(years)
    return {
        "earliest_year": earliest_year,
        "latest_year": latest_year,
        "year_span": latest_year - earliest_year,
    }


def summarize_deep_verifications(internal_data):
    comparisons = Counter()

    for author in internal_data.values():
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

    return dict(comparisons)


def get_internal_data():
    internal_data = {}

    for author_dir in get_author_dirs():
        profile = load_json(author_dir, "profile.json")
        publications = load_json(author_dir, "publications.json")

        try:
            broad_impact = load_json(author_dir, "broad_impact.json")
        except FileNotFoundError:
            broad_impact = []

        internal_data[profile["id"]] = {
            "profile": profile,
            "publications": publications,
            "broad_impact": broad_impact,
        }

    return internal_data


def get_titles_with_markup(internal_data):
    titles_by_markup = {markup_type: [] for markup_type in MARKUP_PATTERNS}

    for author_id, author in internal_data.items():
        for publication in author["publications"]:
            title = publication.get("title", "")

            for markup_type, pattern in MARKUP_PATTERNS.items():
                if pattern.search(title):
                    titles_by_markup[markup_type].append(
                        {
                            "author_id": author_id,
                            "title": title,
                        }
                    )
                    break

    return titles_by_markup


def get_doubled_journals(internal_data):
    doubled = []

    for author_id, author in internal_data.items():
        for publication in author["publications"]:
            journal = publication.get("journal")

            if not journal:
                continue

            words = get_normalized_words(journal)
            half = len(words) // 2

            if words and len(words) % 2 == 0 and words[:half] == words[half:]:
                doubled.append({"author_id": author_id, "journal": journal})

    return doubled


def summarize_duplicate_dois(internal_data):
    records_per_source = Counter()
    duplicate_dois = 0

    for author in internal_data.values():
        records_by_doi = {}

        for publication in author["publications"]:
            doi = normalize_doi(publication.get("doi"))
            if doi:
                records_by_doi.setdefault(doi, []).append(publication.get("source"))

        for sources in records_by_doi.values():
            if len(sources) > 1:
                duplicate_dois += 1
                for source in sources:
                    records_per_source[source] += 1

    return {
        "duplicate_dois": duplicate_dois,
        "records_per_source": dict(records_per_source),
    }


def summarize_journals(internal_data):
    journals = Counter()
    empty = 0

    for author in internal_data.values():
        for publication in author["publications"]:
            journal = publication.get("journal")
            if journal:
                journals[journal] += 1
            else:
                empty += 1

    return {"empty": empty, "journals": dict(journals)}
