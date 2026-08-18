# Scholarix Assessment

- [`analysis/audit/`](analysis/audit/) contains utilities for fetching public data and comparing it against the given dataset

- [`analysis/audit/audit.ipynb`](analysis/audit/audit.ipynb) runs the initial data quality audit and flags potential issues

- [`analysis/product_direction.ipynb`](analysis/product_direction.ipynb) builds on the audit to explore a data quality review workflow


## Setup

### Analysis

Create `.env` at the root with `MAILTO=<your_email>` for public API requests, then run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
