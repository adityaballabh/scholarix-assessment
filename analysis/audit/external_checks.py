from collections import Counter

from comparison_utils import (
    compare_publications,
    compare_texts,
    get_author_keys,
    summarize_publication_comparisons,
)
from fetch_data import normalize_doi
from internal_checks import load_author_records


def get_publications_by_source(authors):
    publications_by_source = {}

    for author_id, author in authors.items():
        for publication in author["publications"]:
            doi = normalize_doi(publication.get("doi"))
            source = publication.get("source")

            if not doi or not source:
                continue

            publications_by_source.setdefault(source, {}).setdefault(doi, []).append({
                "author_id": author_id,
                "publication": publication,
            })

    return publications_by_source


def normalize_crossref_publication(response):
    message = response.get("message") or {}
    titles = message.get("title") or []
    journals = message.get("container-title") or []
    date_parts = (message.get("issued") or {}).get("date-parts") or []
    authors = []

    for author in message.get("author") or []:
        name = " ".join(
            part
            for part in (author.get("given"), author.get("family"))
            if part
        )

        if name:
            authors.append(name)

    return {
        "title": titles[0] if titles else None,
        "year": date_parts[0][0] if date_parts and date_parts[0] else None,
        "journal": journals[0] if journals else None,
        "authors": authors,
    }


def normalize_openalex_publication(response):
    source = (response.get("primary_location") or {}).get("source") or {}

    return {
        "title": response.get("display_name"),
        "year": response.get("publication_year"),
        "journal": source.get("display_name"),
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
                part
                for part in (creator.get("givenName"), creator.get("familyName"))
                if part
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
    return [
        normalize_openalex_publication(response)
        for response in responses or []
    ]


def normalize_crossref_publications(response):
    return [normalize_crossref_publication(response)] if response else []


def normalize_datacite_publications(response):
    return [normalize_datacite_publication(response)] if response else []


def get_source_pairs(stored_publications, source_publications, source_normalizer):
    for doi, stored_records in stored_publications.items():
        source_records = source_normalizer(source_publications.get(doi))

        if not source_records:
            source_records = [{}]

        for stored in stored_records:
            for source in source_records:
                yield doi, stored, source


def compare_source_publications(stored_publications, source_publications, source_normalizer):
    comparisons = []

    for doi, stored, source in get_source_pairs(
        stored_publications,
        source_publications,
        source_normalizer,
    ):
        comparisons.append({
            "author_id": stored["author_id"],
            "doi": doi,
            **compare_publications(stored["publication"], source),
        })

    return comparisons


def compare_openalex_author_publications(authors, source_publications):
    comparisons = []

    for author_id, author in authors.items():
        stored_dois = set()

        for publication in author["publications"]:
            if publication.get("source") != "openalex":
                continue

            doi = normalize_doi(publication.get("doi"))
            if doi:
                stored_dois.add(doi)

        source_publication = source_publications.get(author_id) or {}
        source_dois = source_publication.get("dois") or set()
        shared_dois = stored_dois & source_dois

        comparisons.append({
            "author_id": author_id,
            "source_count": source_publication.get("source_count"),
            "source_doi_count": len(source_dois),
            "stored_doi_count": len(stored_dois),
            "shared_doi_count": len(shared_dois),
            "source_retention": (
                len(shared_dois) / len(source_dois) if source_dois else None
            ),
            "stored_coverage": (
                len(shared_dois) / len(stored_dois) if stored_dois else None
            ),
        })

    return comparisons


def get_orcid_name(record):
    name = (record.get("person") or {}).get("name") or {}
    credit_name = (name.get("credit-name") or {}).get("value")

    if credit_name:
        return credit_name

    return " ".join(
        part.get("value")
        for part in (name.get("given-names") or {}, name.get("family-name") or {})
        if part.get("value")
    ) or None


def compare_orcid_names(authors, orcid_records):
    comparisons = []

    for author_id, author in authors.items():
        orcid_id = author["profile"]["orcid"].get("orcid_id")
        if not orcid_id:
            continue

        record = orcid_records.get(orcid_id) or {}
        profile_name = author["profile"].get("name")
        orcid_name = get_orcid_name(record)

        comparisons.append({
            "author_id": author_id,
            "orcid_id": orcid_id,
            "profile_name": profile_name,
            "orcid_name": orcid_name,
            **compare_texts(profile_name, orcid_name),
        })

    return comparisons


def compare_openalex_semantic_scholar_authors(authors, source_publications):
    comparisons = {}

    for author_id, author in authors.items():
        profile_keys = get_author_keys([author["profile"].get("name")])
        dois = set()
        source_author_ids = set()

        for publication in author["publications"]:
            doi = normalize_doi(publication.get("doi"))
            if doi:
                dois.add(doi)

        for doi in dois:
            source_publication = source_publications.get(doi)
            if not source_publication:
                continue

            for source_author in source_publication.get("authors") or []:
                source_author_id = source_author.get("authorId")
                source_author_keys = get_author_keys([source_author.get("name")])

                if profile_keys & source_author_keys and source_author_id:
                    source_author_ids.add(source_author_id)

        comparisons[author_id] = sorted(source_author_ids)

    return comparisons


def compare_affiliations(authors, openalex_authors):
    match_positions = Counter()
    first_institution_matches = Counter()
    stored_counts = Counter()
    source_counts = Counter()

    for author_id, author in authors.items():
        source_author = openalex_authors.get(author_id) or {}
        institutions = [
            institution.get("display_name")
            for institution in source_author.get("last_known_institutions") or []
            if institution.get("display_name")
        ]
        local_affiliation = author["profile"].get("affiliation")
        first_comparison = compare_texts(
            local_affiliation,
            institutions[0] if institutions else None,
        )

        stored_counts[1 if local_affiliation else 0] += 1
        source_counts[len(institutions)] += 1
        first_institution_matches[first_comparison["status"]] += 1

        match_position = None
        for position, institution in enumerate(institutions, start=1):
            comparison = compare_texts(local_affiliation, institution)

            if comparison["status"] in {"exact", "normalized_match"}:
                match_position = position
                break

        match_positions[match_position] += 1

    return {
        "match_positions": dict(match_positions),
        "first_institution_matches": dict(first_institution_matches),
        "affiliation_counts": {
            "stored": dict(stored_counts),
            "source": dict(source_counts),
        },
    }


def compare_external_sources(authors, data):
    publications_by_source = get_publications_by_source(authors)
    source_publications = {
        "openalex": data["openalex_publications_by_doi"],
        "crossref": data["crossref_publications"],
    }
    source_normalizers = {
        "openalex": normalize_openalex_publications,
        "crossref": normalize_crossref_publications,
    }
    comparisons = {}

    for source, source_records in publications_by_source.items():
        if source not in source_publications:
            continue

        source_comparisons = compare_source_publications(
            source_records,
            source_publications[source],
            source_normalizers[source],
        )
        comparisons[source] = summarize_publication_comparisons(source_comparisons)

    datacite_stored_publications = {
        doi: publications
        for doi, publications in publications_by_source.get("openalex", {}).items()
        if doi in data["datacite_publications"]
    }
    datacite_comparisons = compare_source_publications(
        datacite_stored_publications,
        data["datacite_publications"],
        normalize_datacite_publications,
    )
    comparisons["datacite"] = summarize_publication_comparisons(datacite_comparisons)

    return {
        "publications": comparisons,
        "openalex_author_publications": compare_openalex_author_publications(
            authors,
            data["openalex_publications_by_author"],
        ),
        "orcid_names": compare_orcid_names(authors, data["orcid_records"]),
        "openalex_semantic_scholar_authors": compare_openalex_semantic_scholar_authors(
            authors,
            data["semantic_scholar_publications_by_doi"],
        ),
        "affiliations": compare_affiliations(authors, data["openalex_authors"]),
    }
