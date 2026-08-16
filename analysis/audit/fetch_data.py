import json
import time
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

from requests_cache import CachedSession
from requests_ratelimiter import LimiterAdapter

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = PROJECT_DIR / "dataset"
AUTHORS_DIR = DATASET_DIR / "authors"
AUTHORS_ZIP = DATASET_DIR / "authors.zip"
CACHE_DB_PATH = PROJECT_DIR / "cache" / "http_cache"
ENV_PATH = PROJECT_DIR / ".env"
MAILTO_KEY = "MAILTO"
REQUEST_TIMEOUT_SECONDS = 30

def get_mailto():
    for line in ENV_PATH.read_text().splitlines():
        key, _, value = line.partition("=")

        if key == MAILTO_KEY:
            return value.strip()

    raise RuntimeError(MAILTO_KEY + " is missing from .env")

def create_session():
    CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    session = CachedSession(
        CACHE_DB_PATH,
        backend="sqlite",
        allowable_codes=(200, 302, 404),
        allowable_methods=("GET", "POST"),
    )

    rate_limits = [
        ("https://api.openalex.org", 10),
        ("https://api.crossref.org", 10),
        ("https://pub.orcid.org", 10),
        ("https://api.datacite.org", 2),
        ("https://api.semanticscholar.org", 1),
        ("https://doi.org", 10),
    ]

    for host, rate in rate_limits:
        session.mount(host, LimiterAdapter(per_second=rate))

    return session

def extract_authors():
    if AUTHORS_DIR.exists():
        return

    with ZipFile(AUTHORS_ZIP) as archive:
        archive.extractall(DATASET_DIR)

def get_author_dirs():
    extract_authors()
    return [path for path in AUTHORS_DIR.iterdir() if path.is_dir()]

def load_json(author_dir, filename):
    return json.loads((author_dir / filename).read_text())

def normalize_doi(value):
    if not value:
        return None

    doi = value.strip().lower()
    return doi.rsplit("doi.org/", 1)[-1]

def get_author_data():
    authors = {}

    for author_dir in get_author_dirs():
        profile = load_json(author_dir, "profile.json")
        publications = load_json(author_dir, "publications.json")
        dois = set()

        for publication in publications:
            doi = normalize_doi(publication.get("doi"))
            if doi:
                dois.add(doi)

        authors[profile["id"]] = {"profile": profile, "dois": dois}

    return authors

def get_unique_dois(authors):
    dois = set()

    for author in authors.values():
        dois.update(author["dois"])

    return dois


def get_orcid_ids(authors):
    orcid_ids = set()

    for author in authors.values():
        orcid_id = author["profile"]["orcid"]["orcid_id"]
        if orcid_id:
            orcid_ids.add(orcid_id)

    return orcid_ids


def get_response_json(response, missing_ok=True):
    if response.status_code == 404 and missing_ok:
        return None

    response.raise_for_status()
    return response.json()


def print_progress(name, total, interval, current=0):
    if current % interval == 0 or current == total:
        end = "\n" if current == total else ""
        print(f"\r{name}: {current}/{total}", end=end, flush=True)

def fetch_openalex_authors(session, mailto, author_ids):
    authors = {}
    print_progress("OpenAlex authors", len(author_ids), 10)

    for index, author_id in enumerate(author_ids, start=1):
        response = session.get(
            f"https://api.openalex.org/authors/{author_id}",
            params={"mailto": mailto},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        author = get_response_json(response)
        if author is not None:
            authors[author_id] = author

        print_progress("OpenAlex authors", len(author_ids), 10, index)

    return authors

def fetch_openalex_work_results(session, params, result_name):
    for attempt in range(2):
        results = []
        cursor = "*"
        total = 0

        while cursor:
            page_params = params.copy()
            page_params["cursor"] = cursor
            response = session.get(
                "https://api.openalex.org/works",
                params=page_params,
                force_refresh=attempt == 1,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            payload = get_response_json(response, missing_ok=False)
            results.extend(payload["results"])
            total = payload["meta"]["count"]
            cursor = payload["meta"].get("next_cursor")

        if len(results) == total:
            return results

    raise RuntimeError(f"OpenAlex returned an incomplete {result_name} twice")

def fetch_openalex_publications_by_author(session, mailto, author_ids):
    publications = {}
    print_progress("OpenAlex publications by author", len(author_ids), 2)

    for index, author_id in enumerate(author_ids, start=1):
        results = fetch_openalex_work_results(
            session,
            {
                "filter": f"author.id:{author_id}",
                "select": "doi",
                "per_page": 100,
                "mailto": mailto,
            },
            "author publication list",
        )
        dois = set()

        for publication in results:
            doi = normalize_doi(publication.get("doi"))
            if doi:
                dois.add(doi)

        publications[author_id] = {
            "source_count": len(results),
            "dois": dois,
        }
        print_progress("OpenAlex publications by author", len(author_ids), 2, index)

    return publications

def fetch_openalex_publications_by_doi(session, mailto, dois):
    batch_size = 100
    dois = sorted(dois)
    publications = {}
    print_progress("OpenAlex publications by DOI", len(dois), 100)

    for start in range(0, len(dois), batch_size):
        batch = dois[start : start + batch_size]
        params = {
            "filter": "doi:" + "|".join(batch),
            "per_page": batch_size,
            "mailto": mailto,
        }
        results = fetch_openalex_work_results(session, params, "DOI publication batch")

        for publication in results:
            doi = normalize_doi(publication.get("doi"))
            if doi:
                if doi not in publications:
                    publications[doi] = []

                publications[doi].append(publication)

        print_progress("OpenAlex publications by DOI", len(dois), 100, start + len(batch))

    return publications

def fetch_semantic_scholar_publications_by_doi(session, dois):
    batch_size = 500
    dois = sorted(dois)
    publications = {}
    print_progress("Semantic Scholar publications by DOI", len(dois), 500)

    for start in range(0, len(dois), batch_size):
        batch = dois[start : start + batch_size]

        for attempt in range(4):
            time.sleep(5 * attempt)

            response = session.post(
                "https://api.semanticscholar.org/graph/v1/paper/batch",
                params={"fields": "externalIds,title,year,authors.authorId,authors.name"},
                json={"ids": [f"DOI:{doi}" for doi in batch]},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code != 429:
                results = get_response_json(response, missing_ok=False)
                break
        else:
            raise RuntimeError("Semantic Scholar rate-limited a DOI publication batch four times")

        for publication in results:
            if not publication:
                continue

            doi = normalize_doi((publication.get("externalIds") or {}).get("DOI"))
            if doi:
                publications[doi] = publication

        print_progress(
            "Semantic Scholar publications by DOI",
            len(dois),
            500,
            start + len(batch),
        )

    return publications


def fetch_crossref_publications(session, mailto, dois):
    publications = {}
    print_progress("Crossref publications", len(dois), 100)

    for index, doi in enumerate(dois, start=1):
        response = session.get(
            f"https://api.crossref.org/works/{quote(doi, safe='')}",
            params={"mailto": mailto},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        publication = get_response_json(response)
        if publication is not None:
            publications[doi] = publication

        print_progress("Crossref publications", len(dois), 100, index)

    return publications

def fetch_orcid_records(session, orcid_ids):
    records = {}
    print_progress("ORCID records", len(orcid_ids), 10)

    for index, orcid_id in enumerate(orcid_ids, start=1):
        response = session.get(
            f"https://pub.orcid.org/v3.0/{orcid_id}/record",
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        record = get_response_json(response)
        if record is not None:
            records[orcid_id] = record

        print_progress("ORCID records", len(orcid_ids), 10, index)

    return records

def fetch_datacite_publications(session, dois):
    publications = {}
    print_progress("DataCite publications", len(dois), 10)

    for index, doi in enumerate(dois, start=1):
        response = session.get(
            f"https://api.datacite.org/dois/{quote(doi, safe='/')}",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        publication = get_response_json(response)
        if publication is not None:
            publications[doi] = publication

        print_progress("DataCite publications", len(dois), 10, index)

    return publications


def fetch_doi_resolutions(session, dois):
    resolutions = {}
    print_progress("DOI resolutions", len(dois), 10)

    for index, doi in enumerate(dois, start=1):
        response = session.get(
            f"https://doi.org/{quote(doi, safe='/')}",
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        status = response.status_code
        redirect_url = response.headers.get("Location")
        resolutions[doi] = {
            "status": status,
            "redirected": 300 <= status < 400 and bool(redirect_url),
            "redirect_url": redirect_url,
        }
        print_progress("DOI resolutions", len(dois), 10, index)

    return resolutions

def fetch_all():
    mailto = get_mailto()
    session = create_session()

    authors = get_author_data()
    dois = get_unique_dois(authors)
    orcid_ids = get_orcid_ids(authors)
    print("Fetching")
    openalex_authors = fetch_openalex_authors(session, mailto, authors.keys())
    openalex_publications_by_author = fetch_openalex_publications_by_author(
        session, mailto, authors.keys()
    )
    orcid_records = fetch_orcid_records(session, orcid_ids)
    openalex_publications_by_doi = fetch_openalex_publications_by_doi(session, mailto, dois)
    crossref_publications = fetch_crossref_publications(session, mailto, dois)
    # DataCite fills DOI records that are missing from Crossref
    crossref_missing_dois = dois - crossref_publications.keys()
    datacite_publications = fetch_datacite_publications(session, crossref_missing_dois)
    unresolved_dois = crossref_missing_dois - datacite_publications.keys()
    doi_resolutions = fetch_doi_resolutions(session, unresolved_dois)
    semantic_scholar_publications_by_doi = fetch_semantic_scholar_publications_by_doi(session, dois)

    return {
        "dois": dois,
        "openalex_authors": openalex_authors,
        "openalex_publications_by_author": openalex_publications_by_author,
        "orcid_records": orcid_records,
        "openalex_publications_by_doi": openalex_publications_by_doi,
        "crossref_publications": crossref_publications,
        "datacite_publications": datacite_publications,
        "doi_resolutions": doi_resolutions,
        "semantic_scholar_publications_by_doi": semantic_scholar_publications_by_doi,
    }
