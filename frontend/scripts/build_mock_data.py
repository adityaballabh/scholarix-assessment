import hashlib
import json
from collections import Counter
from pathlib import Path

from mock_data_config import S2_AUTHOR_CANDIDATES

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
AUTHORS_DIR = PROJECT_DIR / "dataset" / "authors"
OUTPUT_DIR = PROJECT_DIR / "frontend" / "src" / "mock"
AUDIT_FETCHED_AT = "2026-08-14T09:15:00Z"

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def build_case_id(author_slug):
    value = f"identity|{author_slug}"
    digest = hashlib.sha1(value.encode()).hexdigest()
    return "c-" + digest[:10]


def normalize_institution(institution):
    return " ".join((institution or "").casefold().split())


def get_unique_institutions(orcid):
    institutions = []
    normalized_institutions = set()

    for institution in orcid.get("current_institution") or []:
        normalized = normalize_institution(institution)
        if normalized and normalized not in normalized_institutions:
            institutions.append(institution)
            normalized_institutions.add(normalized)

    return institutions


def get_authors():
    authors = []

    for author_dir in sorted(AUTHORS_DIR.iterdir()):
        if not author_dir.is_dir():
            continue

        try:
            profile = json.loads((author_dir / "profile.json").read_text())
            publications = json.loads((author_dir / "publications.json").read_text())
        except (OSError, ValueError):
            continue

        authors.append(
            {
                "slug": author_dir.name,
                "profile": profile,
                "publications": publications,
            }
        )

    return authors


def build_source_ref(entity_type, record_id):
    return {"entity_type": entity_type, "id": record_id}


def build_evidence(
    source, source_refs, field, value, value_state, interpretation, fetch_status="success"
):
    return {
        "source": source,
        "source_refs": source_refs,
        "fetched_at": AUDIT_FETCHED_AT if fetch_status != "never_attempted" else None,
        "fetch_status": fetch_status,
        "field": field,
        "value": value,
        "value_state": value_state,
        "interpretation": interpretation,
    }


def build_identity_case(author):
    profile = author["profile"]
    publications = author["publications"]
    name = profile["name"]

    candidates = [
        {
            "id": candidate["id"],
            "share": candidate["share"],
            "first_year": candidate["first_year"],
            "last_year": candidate["last_year"],
            "publications": candidate["publications"],
        }
        for candidate in S2_AUTHOR_CANDIDATES.get(name, [])
    ]
    candidates.sort(key=lambda candidate: candidate["share"], reverse=True)
    if not candidates:
        return None

    distinct_total = len(candidates)
    orcid = profile.get("orcid") or {}

    evidence = [
        build_evidence(
            "semantic_scholar",
            [build_source_ref("author", candidate["id"]) for candidate in candidates],
            "author_identity",
            f"{distinct_total} S2 IDs for publications matching this name",
            "conflict",
            "",
        ),
        build_evidence(
            "openalex",
            [build_source_ref("author", profile["id"])],
            "canonical_name",
            name,
            "supports",
            "",
        ),
        build_evidence(
            "openalex",
            [build_source_ref("author", profile["id"])],
            "affiliation",
            profile.get("affiliation"),
            "supports",
            "",
        ),
    ]

    institutions = get_unique_institutions(orcid)
    if orcid.get("orcid_id") and institutions:
        agrees = normalize_institution(profile.get("affiliation")) in {
            normalize_institution(institution) for institution in institutions
        }
        evidence.append(
            build_evidence(
                "orcid",
                [build_source_ref("author", orcid["orcid_id"])],
                "affiliation",
                "; ".join(institutions),
                "supports" if agrees else "conflict",
                ""
                if agrees
                else "Different institutions can indicate multiple appointments or timing instead of an incorrect value",
            )
        )
    elif orcid.get("orcid_id"):
        evidence.append(
            build_evidence(
                "orcid",
                [build_source_ref("author", orcid["orcid_id"])],
                "affiliation",
                None,
                "missing",
                "The ORCID record does not provide an institution.",
            )
        )
    else:
        evidence.append(
            build_evidence(
                "orcid", [], "affiliation", None, "missing", "",
                fetch_status="never_attempted",
            )
        )

    # Google Scholar was rate limited for every author in the dataset
    evidence.append(
        build_evidence(
            "google_scholar", [], "profile_link", None, "unverifiable", "",
            fetch_status="rate_limited",
        )
    )
    top_share = candidates[0]["share"]

    return {
        "id": build_case_id(author["slug"]),
        "status": "pending",
        "priority": "high" if distinct_total >= 11 else "medium",
        "target": {
            "author_slug": author["slug"],
            "author_name": name,
            "openalex_id": profile.get("id"),
        },
        "affected_count": len(publications),
        "evidence": evidence,
        "detail": {
            "candidate_ids": candidates,
            "top_share": top_share,
            "profile_topics": profile.get("topics") or [],
        },
    }


def build_overview(cases, authors):
    case_slugs = {case["target"]["author_slug"] for case in cases}
    publications_by_slug = {author["slug"]: len(author["publications"]) for author in authors}
    profiles_by_slug = {author["slug"]: author["profile"] for author in authors}

    verified_orcid = sum(
        1
        for slug in case_slugs
        if (profiles_by_slug.get(slug, {}).get("orcid") or {}).get("verified")
    )
    author_count = len(case_slugs)

    return {
        "authors": author_count,
        "publications": sum(publications_by_slug.get(slug, 0) for slug in case_slugs),
        "authors_audited": len(authors),
        "publications_audited": sum(publications_by_slug.values()),
        "audited_at": AUDIT_FETCHED_AT,
        "open_cases": len(cases),
        "by_priority": dict(Counter(case["priority"] for case in cases)),
        "sources": [
            {
                "source": "semantic_scholar",
                "fetched_at": AUDIT_FETCHED_AT,
                "state": "success",
                "note": f"Candidates found for all {author_count} profiles",
            },
            {
                "source": "openalex",
                "fetched_at": AUDIT_FETCHED_AT,
                "state": "success",
                "note": f"Records found for all {author_count} profiles",
            },
            {
                "source": "orcid",
                "fetched_at": AUDIT_FETCHED_AT,
                "state": "success",
                "note": f"{verified_orcid} of {author_count} have a verified ORCID",
            },
            {
                "source": "google_scholar",
                "fetched_at": AUDIT_FETCHED_AT,
                "state": "rate_limited",
                "note": f"HTTP 429 for all {author_count}. No links verified",
            },
        ],
    }


def write_mock_data(cases, overview):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "cases.json").write_text(json.dumps({"cases": cases}, indent=1))
    (OUTPUT_DIR / "overview.json").write_text(json.dumps(overview, indent=1))


def print_summary(cases):
    case_slugs = {case["target"]["author_slug"] for case in cases}

    print(f"authors      {len(case_slugs)}")
    print(f"cases        {len(cases)}")
    print(f"wrote        {OUTPUT_DIR}")


def build_mock_data():
    authors = get_authors()

    cases = []
    for author in authors:
        case = build_identity_case(author)
        if case:
            cases.append(case)

    cases.sort(key=lambda case: (PRIORITY_RANK[case["priority"]], -case["affected_count"]))

    write_mock_data(cases, build_overview(cases, authors))
    print_summary(cases)


if __name__ == "__main__":
    build_mock_data()
