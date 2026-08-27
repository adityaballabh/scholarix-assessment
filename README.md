# Scholarix Assessment

## Overview

This project audits the given researcher dataset for quality issues and uses the findings to build **Merge Review**. The app allows reviewers to investigate profiles that might represent more than one author.

### Analysis

- [`analysis/audit/`](analysis/audit/) contains utilities for fetching public data and comparing it against the given [`dataset`](dataset/)

- [`analysis/audit/audit.ipynb`](analysis/audit/audit.ipynb) runs the initial data quality audit and flags potential issues

- [`analysis/product_direction.ipynb`](analysis/product_direction.ipynb) builds on the audit to explore a data quality review workflow

- [`dataset/`](dataset/) contains 50 author profiles, publications, and broad-impact files

### App

- [`frontend/`](frontend/) and [`backend/`](backend/) contain **Merge Review**, which prioritizes profiles for review and compares dataset records against evidence from public sources

- Reviewers can record decisions and notes, with history available in **Activity**

- Evidence and decision history for all cases matching the filters (or a single case) can be exported as JSON

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

Then open <http://localhost:8080> and click _fetch data_ on the first run, which takes ~3 minutes.

### Optional

Create `.env` at the root with `MAILTO=<your_email>` as identification for public API requests, which can lead to higher rate limits or quicker responses

## Sources

### App

- [OpenAlex](https://openalex.org) for canonical names, affiliations, and publication records

- [Semantic Scholar](https://semanticscholar.org) for author identity

- [ORCID](https://orcid.org) for affiliations

### Analysis

The analysis uses the sources above along with [Crossref](https://www.crossref.org/) and [DataCite](https://datacite.org/) for DOI and publication metadata

## Limitations

- The app requires an initial evidence fetch on the first run to build the review queue

- [`dataset/`](dataset/) can't be changed once the app image is built

- The queue is rebuilt when the scoring settings change or when new evidence is fetched for an author, since scores are relative

- Review decisions are just stored without changing the underlying author profiles

- Decision making is blocked for all users whenever a fetch is in progress

- S2 requests use the shared anonymous pool, so repeated full fetches can hit rate limits
