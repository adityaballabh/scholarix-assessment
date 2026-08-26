# Scholarix Assessment

## Overview

### Analysis

- [`analysis/audit/`](analysis/audit/) contains utilities for fetching public data and comparing it against the given [`dataset`](dataset/)

- [`analysis/audit/audit.ipynb`](analysis/audit/audit.ipynb) runs the initial data quality audit and flags potential issues

- [`analysis/product_direction.ipynb`](analysis/product_direction.ipynb) builds on the audit to explore a data quality review workflow

- [`dataset/`](dataset/) contains 50 author profiles, publications, and broad-impact files

### App

- [`frontend/`](frontend/) and [`backend/`](backend/) contain the app that lets reviewers decide if an author should be split based on external evidence

    Evidence for all authors matching the filters (or a single case) can be exported as JSON

## Setup

### Analysis

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### App

```bash
docker compose up
```

Then open <http://localhost:8080> and click *fetch data*, which takes ~3 minutes

### Optional

Create `.env` at the root with `MAILTO=<your_email>` as identification for public API requests, which can lead to quicker responses or higher rate limits

## Sources

- [OpenAlex](https://openalex.org) for canonical names, affiliations, and publication records

- [Semantic Scholar](https://semanticscholar.org) for author identity

- [ORCID](https://orcid.org) for affiliations

## Limitations

- The app currently requires an initial fetch on startup

- [`dataset/`](dataset/) can't be changed once the app image is built

- The queue is rebuilt when the scoring settings change or when new evidence is fetched for an author, since scores are relative

- The app only lets reviewers record decisions instead of actually splitting authors

- Decision making is blocked for all users whenever a fetch is in progress

- S2 requests use the shared anonymous pool, so repeated full fetches can hit rate limits
