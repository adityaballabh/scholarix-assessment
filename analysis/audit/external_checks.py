from collections import Counter

from comparison_utils import (
    compare_publications,
    compare_texts,
    get_author_keys,
    get_publication_authors,
    summarize_publication_comparisons,
)
from fetch_data import normalize_doi
from internal_checks import get_year_span


def get_publications_by_source(internal_data):
    publications_by_source = {}

    for author_id, author in internal_data.items():
        for publication in author["publications"]:
            doi = normalize_doi(publication.get("doi"))
            source = publication.get("source")

            if not doi or not source:
                continue

            publications_by_source.setdefault(source, {}).setdefault(doi, []).append(
                {
                    "author_id": author_id,
                    "publication": publication,
                }
            )

    return publications_by_source


def normalize_crossref_publication(response):
    message = response.get("message") or {}
    titles = message.get("title") or []
    journals = message.get("container-title") or []
    date_parts = (message.get("issued") or {}).get("date-parts") or []
    authors = []

    for author in message.get("author") or []:
        name = " ".join(part for part in (author.get("given"), author.get("family")) if part)

        if name:
            authors.append(name)

    return {
        "title": titles[0] if titles else None,
        "year": date_parts[0][0] if date_parts and date_parts[0] else None,
        "journal": journals[0] if journals else None,
        "authors": authors,
    }


def normalize_openalex_publication(response):
    venue = (response.get("primary_location") or {}).get("source") or {}

    return {
        "title": response.get("display_name"),
        "year": response.get("publication_year"),
        "journal": venue.get("display_name"),
        "authors": [
            (authorship.get("author") or {}).get("display_name")
            for authorship in response.get("authorships") or []
            if (authorship.get("author") or {}).get("display_name")
        ],
    }


def normalize_datacite_publication(response):
    attributes = (response.get("data") or {}).get("attributes") or {}
    titles = attributes.get("titles") or []
    authors = []
    journal = None

    # Prefer explicit IsPublishedIn metadata
    for related_item in attributes.get("relatedItems") or []:
        if related_item.get("relationType") != "IsPublishedIn":
            continue

        related_titles = related_item.get("titles") or []
        if related_titles and related_titles[0].get("title"):
            journal = related_titles[0]["title"]
            break

    if not journal:
        journal = (attributes.get("container") or {}).get("title")

    for creator in attributes.get("creators") or []:
        if creator.get("nameType") == "Personal" and creator.get("familyName"):
            name = " ".join(
                part for part in (creator.get("givenName"), creator.get("familyName")) if part
            )
        else:
            name = creator.get("name")

        if name:
            authors.append(name)

    return {
        "title": titles[0].get("title") if titles else None,
        "year": attributes.get("publicationYear"),
        "journal": journal,
        "authors": authors,
    }


def normalize_openalex_publications(responses):
    return [normalize_openalex_publication(response) for response in responses or []]


def normalize_crossref_publications(response):
    return [normalize_crossref_publication(response)] if response else []


def normalize_datacite_publications(response):
    return [normalize_datacite_publication(response)] if response else []


def get_internal_external_pairs(internal_publications, external_publications, external_normalizer):
    for doi, internal_records in internal_publications.items():
        external_records = external_normalizer(external_publications.get(doi))

        if not external_records:
            external_records = [{}]

        for internal in internal_records:
            for external in external_records:
                yield doi, internal, external


def compare_internal_to_external(internal_publications, external_publications, external_normalizer):
    comparisons = []

    for doi, internal, external in get_internal_external_pairs(
        internal_publications,
        external_publications,
        external_normalizer,
    ):
        comparisons.append(
            {
                "author_id": internal["author_id"],
                "doi": doi,
                **compare_publications(internal["publication"], external),
            }
        )

    return comparisons


def compare_openalex_author_publications(internal_data, external_publications):
    comparisons = []

    for author_id, author in internal_data.items():
        internal_dois = set()

        for publication in author["publications"]:
            if publication.get("source") != "openalex":
                continue

            doi = normalize_doi(publication.get("doi"))
            if doi:
                internal_dois.add(doi)

        external_publication = external_publications.get(author_id) or {}
        external_dois = external_publication.get("dois") or set()
        shared_dois = internal_dois & external_dois

        comparisons.append(
            {
                "author_id": author_id,
                "external_publication_count": external_publication.get("source_count"),
                "external_doi_count": len(external_dois),
                "internal_doi_count": len(internal_dois),
                "shared_doi_count": len(shared_dois),
                "openalex_dois_found_internally": (
                    len(shared_dois) / len(external_dois) if external_dois else None
                ),
                "internal_dois_found_in_openalex": (
                    len(shared_dois) / len(internal_dois) if internal_dois else None
                ),
            }
        )

    return comparisons


def compare_author_list_lengths(internal_data, external_data):
    comparisons = []
    crossref_publications = external_data["crossref_publications"]

    for author_id, author in internal_data.items():
        profile_keys = get_author_keys([author["profile"].get("name")])
        openalex_by_doi = {}
        crossref_by_doi = {}

        for publication in author["publications"]:
            doi = normalize_doi(publication.get("doi"))
            if not doi:
                continue

            if publication.get("source") == "openalex":
                openalex_by_doi[doi] = publication
            elif publication.get("source") == "crossref":
                crossref_by_doi[doi] = publication

        for doi in openalex_by_doi.keys() & crossref_by_doi.keys():
            openalex_authors = get_publication_authors(openalex_by_doi[doi]) or []
            internal_crossref_authors = get_publication_authors(crossref_by_doi[doi]) or []
            external_crossref_authors = []

            if doi in crossref_publications:
                external_crossref_authors = normalize_crossref_publication(
                    crossref_publications[doi]
                )["authors"]

            comparisons.append(
                {
                    "author_id": author_id,
                    "doi": doi,
                    "internal_openalex": len(openalex_authors),
                    "internal_crossref": len(internal_crossref_authors),
                    "external_crossref": len(external_crossref_authors),
                    "profile_author_in_internal_openalex": bool(
                        profile_keys & get_author_keys(openalex_authors)
                    ),
                    "profile_author_in_internal_crossref": bool(
                        profile_keys & get_author_keys(internal_crossref_authors)
                    ),
                }
            )

    return comparisons


def get_orcid_name(record):
    name = (record.get("person") or {}).get("name") or {}
    credit_name = (name.get("credit-name") or {}).get("value")

    if credit_name:
        return credit_name

    return (
        " ".join(
            part.get("value")
            for part in (name.get("given-names") or {}, name.get("family-name") or {})
            if part.get("value")
        )
        or None
    )


def compare_orcid_names(internal_data, orcid_data):
    comparisons = []

    for author_id, author in internal_data.items():
        orcid_id = author["profile"]["orcid"].get("orcid_id")
        if not orcid_id:
            continue

        record = orcid_data.get(orcid_id) or {}
        profile_name = author["profile"].get("name")
        orcid_name = get_orcid_name(record)

        comparisons.append(
            {
                "author_id": author_id,
                "orcid_id": orcid_id,
                "profile_name": profile_name,
                "orcid_name": orcid_name,
                **compare_texts(profile_name, orcid_name),
            }
        )

    return comparisons


def get_orcid_status(internal_orcid, external_orcid):
    if internal_orcid:
        return "present"

    return "recoverable" if external_orcid else "missing"


def compare_orcid_recoverability(internal_data, openalex_data):
    comparisons = []

    for author_id, author in internal_data.items():
        internal_orcid = author["profile"]["orcid"].get("orcid_id")
        openalex_author = openalex_data.get(author_id) or {}
        external_orcid = openalex_author.get("orcid")

        comparisons.append(
            {
                "author_id": author_id,
                "internal_orcid": internal_orcid,
                "external_orcid": external_orcid,
                "status": get_orcid_status(internal_orcid, external_orcid),
            }
        )

    return comparisons


def compare_semantic_scholar_authors(internal_data, external_publications):
    comparisons = []

    for author_id, author in internal_data.items():
        profile_keys = get_author_keys([author["profile"].get("name")])
        publications_by_author_id = {}

        for publication in author["publications"]:
            doi = normalize_doi(publication.get("doi"))
            if not doi:
                continue

            external_publication = external_publications.get(doi)
            if not external_publication:
                continue

            for external_author in external_publication.get("authors") or []:
                external_author_id = external_author.get("authorId")
                external_author_keys = get_author_keys([external_author.get("name")])

                if profile_keys & external_author_keys and external_author_id:
                    publications_by_author_id.setdefault(external_author_id, {})[doi] = (
                        external_publication.get("title")
                    )

        total_matches = sum(
            len(publications) for publications in publications_by_author_id.values()
        )

        for external_author_id, publications in sorted(publications_by_author_id.items()):
            sample_title = next((title for title in publications.values() if title), None)

            comparisons.append(
                {
                    "author_id": author_id,
                    "semantic_scholar_author_id": external_author_id,
                    "matched_publication_share_percent": round(
                        100 * len(publications) / total_matches,
                        1,
                    ),
                    "sample_title": sample_title,
                }
            )

    return comparisons


def compare_affiliations(internal_data, openalex_data):
    match_positions = Counter()
    last_known_institution_counts = Counter()
    historical_affiliation_counts = Counter()

    for author_id, author in internal_data.items():
        openalex_author = openalex_data.get(author_id) or {}
        institutions = [
            institution.get("display_name")
            for institution in openalex_author.get("last_known_institutions") or []
            if institution.get("display_name")
        ]
        historical_affiliations = [
            affiliation["institution"]["display_name"]
            for affiliation in openalex_author.get("affiliations") or []
            if (affiliation.get("institution") or {}).get("display_name")
        ]
        internal_affiliation = author["profile"].get("affiliation")

        last_known_institution_counts[len(institutions)] += 1
        historical_affiliation_counts[len(historical_affiliations)] += 1

        match_position = None
        for position, institution in enumerate(institutions, start=1):
            comparison = compare_texts(internal_affiliation, institution)

            if comparison["status"] in {"exact", "normalized_match"}:
                match_position = position
                break

        match_positions[match_position] += 1

    return {
        "match_positions": dict(match_positions),
        "affiliation_counts": {
            "last_known_institutions": dict(last_known_institution_counts),
            "historical_affiliations": dict(historical_affiliation_counts),
        },
    }


def compare_year_spans(internal_data, openalex_data):
    comparisons = []

    for author_id, author in internal_data.items():
        openalex_author = openalex_data.get(author_id) or {}

        comparisons.append(
            {
                "author_id": author_id,
                "internal": get_year_span(author["profile"].get("counts_by_year")),
                "external": get_year_span(openalex_author.get("counts_by_year")),
            }
        )

    return comparisons


def summarize_doi_soundness(external_data):
    crossref = external_data["crossref_publications"]
    datacite = external_data["datacite_publications"]
    resolutions = external_data["doi_resolutions"]

    counts = Counter()
    for doi in external_data["dois"]:
        if doi in crossref:
            counts["crossref"] += 1
        elif doi in datacite:
            counts["datacite_not_crossref"] += 1
        elif (resolutions.get(doi) or {}).get("redirected"):
            counts["resolves_only"] += 1
        else:
            counts["unresolved"] += 1

    return dict(counts)


def compare_against_external_data(internal_data, external_data):
    publications_by_source = get_publications_by_source(internal_data)
    external_publications = {
        "openalex": external_data["openalex_publications_by_doi"],
        "crossref": external_data["crossref_publications"],
    }
    external_normalizers = {
        "openalex": normalize_openalex_publications,
        "crossref": normalize_crossref_publications,
    }
    comparisons = {}

    for source, internal_records in publications_by_source.items():
        if source not in external_publications:
            continue

        source_comparisons = compare_internal_to_external(
            internal_records,
            external_publications[source],
            external_normalizers[source],
        )
        comparisons[source] = summarize_publication_comparisons(source_comparisons)

    datacite_internal_publications = {
        doi: publications
        for doi, publications in publications_by_source.get("openalex", {}).items()
        if doi in external_data["datacite_publications"]
    }
    datacite_comparisons = compare_internal_to_external(
        datacite_internal_publications,
        external_data["datacite_publications"],
        normalize_datacite_publications,
    )
    comparisons["datacite"] = summarize_publication_comparisons(datacite_comparisons)

    return {
        "field_agreement": comparisons,
        "publication_coverage": compare_openalex_author_publications(
            internal_data,
            external_data["openalex_publications_by_author"],
        ),
        "orcid_names": compare_orcid_names(internal_data, external_data["orcid_records"]),
        "orcid_recoverability": compare_orcid_recoverability(
            internal_data,
            external_data["openalex_authors"],
        ),
        "semantic_scholar_author_evidence": compare_semantic_scholar_authors(
            internal_data,
            external_data["semantic_scholar_publications_by_doi"],
        ),
        "affiliations": compare_affiliations(internal_data, external_data["openalex_authors"]),
        "year_spans": compare_year_spans(internal_data, external_data["openalex_authors"]),
    }
