import json
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
        allowable_codes=(200, 404),
    )

    rate_limits = [
        ("https://api.openalex.org", 10),
        ("https://api.crossref.org", 10),
        ("https://pub.orcid.org", 10),
        ("https://api.datacite.org", 2),
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


def fetch_openalex_authors(author_ids):
    authors = {}
    print_progress("OpenAlex authors", len(author_ids), 10)

    for index, author_id in enumerate(author_ids, start=1):
        response = session.get(
            f"https://api.openalex.org/authors/{author_id}",
            params={"mailto": MAILTO},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        author = get_response_json(response)
        if author is not None:
            authors[author_id] = author

        print_progress("OpenAlex authors", len(author_ids), 10, index)

    return authors


def fetch_openalex_publications(dois):
    batch_size = 100
    dois = sorted(dois)
    publications = {}
    print_progress("OpenAlex publications", len(dois), 100)

    for start in range(0, len(dois), batch_size):
        batch = dois[start : start + batch_size]
        params = {
            "filter": "doi:" + "|".join(batch),
            "per_page": batch_size,
            "mailto": MAILTO,
        }
        results = []
        page = 1
        total = None

        # A DOI can match more than one OpenAlex work, so a batch could need pages
        while total is None or len(results) < total:
            page_params = params.copy()
            if page > 1:
                page_params["page"] = page

            for attempt in range(2):
                response = session.get(
                    "https://api.openalex.org/works",
                    params=page_params,
                    force_refresh=attempt == 1,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                payload = get_response_json(response, missing_ok=False)
                total = payload["meta"]["count"]
                page_results = payload["results"]
                expected = min(batch_size, total - len(results))

                if len(page_results) == expected:
                    break

                session.cache.delete(response.cache_key)
            else:
                raise RuntimeError("OpenAlex returned an incomplete page twice")

            results.extend(page_results)
            page += 1

        for publication in results:
            doi = normalize_doi(publication.get("doi"))
            if doi:
                if doi not in publications:
                    publications[doi] = []

                publications[doi].append(publication)

        print_progress("OpenAlex publications", len(dois), 100, start + len(batch))

    return publications


def fetch_crossref_publications(dois):
    publications = {}
    print_progress("Crossref publications", len(dois), 100)

    for index, doi in enumerate(dois, start=1):
        response = session.get(
            f"https://api.crossref.org/works/{quote(doi, safe='')}",
            params={"mailto": MAILTO},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        publication = get_response_json(response)
        if publication is not None:
            publications[doi] = publication

        print_progress("Crossref publications", len(dois), 100, index)

    return publications


def fetch_orcid_records(orcid_ids):
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


def fetch_datacite_publications(dois):
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

def fetch_all():
    authors = get_author_data()
    dois = get_unique_dois(authors)
    orcid_ids = get_orcid_ids(authors)

    openalex_authors = fetch_openalex_authors(authors.keys())
    orcid_records = fetch_orcid_records(orcid_ids)
    openalex_publications = fetch_openalex_publications(dois)
    crossref_publications = fetch_crossref_publications(dois)
    # DataCite fills DOI records that are missing from Crossref
    crossref_missing_dois = dois - crossref_publications.keys()
    datacite_publications = fetch_datacite_publications(crossref_missing_dois)

    return {
        "authors": authors,
        "dois": dois,
        "openalex_authors": openalex_authors,
        "orcid_records": orcid_records,
        "openalex_publications": openalex_publications,
        "crossref_publications": crossref_publications,
        "datacite_publications": datacite_publications,
    }

MAILTO = get_mailto()
session = create_session()
