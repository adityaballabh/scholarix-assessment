import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listCases, queueExportUrl } from "../../api/client";
import Select from "../../components/Select";
import type { SortDirection } from "../../components/SortHeader";
import type { ValidationCase } from "../../api/types";
import { updateSortParams } from "../../lib/sortParams";
import {
  defaultStatusForScope,
  getStatusFilter,
  readOption,
  readQueueScope,
  statusOptions,
  statusOrder,
} from "./filters";
import QueueTable from "./QueueTable";
import type { QueueSortColumn } from "./QueueTable";
import styles from "./QueuePage.module.css";

const STALE_DELAY_MS = 500;
const SEARCH_DEBOUNCE_MS = 200;

export default function QueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [cases, setCases] = useState<ValidationCase[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [anyCasesExist, setAnyCasesExist] = useState(true);
  const [stale, setStale] = useState(false);

  const query = searchParams.get("query") ?? "";
  const rawStatus = searchParams.get("status");
  const rawScope = searchParams.get("scope");
  const scope = readQueueScope(rawScope);
  const defaultStatus = defaultStatusForScope(scope);
  const status = readOption(rawStatus, statusOptions, defaultStatus);
  const rowSearch = searchParams.toString();
  const rawSort = searchParams.get("sort");
  const sort: QueueSortColumn | "" =
    rawSort === "score" ||
    rawSort === "share" ||
    rawSort === "candidates" ||
    rawSort === "publications" ||
    rawSort === "status"
      ? rawSort
      : "";
  const direction: SortDirection =
    searchParams.get("dir") === "asc" ? "asc" : "desc";

  const [draftQuery, setDraftQuery] = useState(query);

  useEffect(() => {
    let active = true;

    listCases({ scope })
      .then((allCases) => {
        if (active) setAnyCasesExist(allCases.length > 0);
      })
      .catch(() => {
        // The filtered request below owns the visible error state.
      });

    return () => {
      active = false;
    };
  }, [scope]);

  useEffect(() => {
    if (!loading) {
      setStale(false);
      return;
    }

    const timer = setTimeout(() => setStale(true), STALE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [loading]);

  useEffect(() => {
    const invalid = [
      rawStatus !== null && rawStatus !== status ? "status" : null,
      rawScope !== null && rawScope !== scope ? "scope" : null,
    ].filter(Boolean) as string[];

    if (invalid.length === 0) return;

    setSearchParams(
      (previous) => {
        const nextParams = new URLSearchParams(previous);
        invalid.forEach((name) => nextParams.delete(name));
        return nextParams;
      },
      { replace: true },
    );
  }, [rawStatus, rawScope, scope, status]);

  useEffect(() => {
    setDraftQuery(query);
  }, [query]);

  useEffect(() => {
    if (draftQuery === query) return;

    const timer = setTimeout(
      () => updateFilter("query", draftQuery),
      SEARCH_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [draftQuery]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);

    listCases({
      query: query || undefined,
      scope,
      status: getStatusFilter(status),
    })
      .then((reviewCases) => {
        if (!active) return;
        setCases(reviewCases);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setError(true);
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [query, scope, status]);

  function orderCases(rows: ValidationCase[]): ValidationCase[] {
    if (!sort) return rows;

    const sortValue = (reviewCase: ValidationCase): number => {
      switch (sort) {
        case "score":
          return reviewCase.priority_score;
        case "share":
          return reviewCase.detail.top_share ?? 0;
        case "candidates":
          return reviewCase.detail.candidate_ids.length;
        case "status":
          return statusOrder.indexOf(reviewCase.status);
        default:
          return reviewCase.affected_count;
      }
    };

    return [...rows].sort((a, b) => {
      const gap = sortValue(a) - sortValue(b);
      return direction === "asc" ? gap : -gap;
    });
  }

  function applySort(column: QueueSortColumn, next: SortDirection | null) {
    setSearchParams((previous) => updateSortParams(previous, column, next), {
      replace: true,
    });
  }

  function updateFilter(name: string, value: string) {
    setSearchParams(
      (previous) => {
        const nextParams = new URLSearchParams(previous);

        if (value && !(name === "status" && value === defaultStatus)) {
          nextParams.set(name, value);
        } else {
          nextParams.delete(name);
        }

        return nextParams;
      },
      { replace: true },
    );
  }

  const filtered = Boolean(query || status !== defaultStatus);

  return (
    <section className={styles.page}>
      <div className={styles.filters}>
        <label className={styles.searchLabel}>
          <span className={styles.srOnly}>Search reviews</span>
          <input
            className={styles.search}
            type="search"
            value={draftQuery}
            placeholder="search author"
            onChange={(event) => setDraftQuery(event.target.value)}
          />
        </label>
        <Select
          label="Status"
          value={status}
          options={statusOptions}
          onChange={(value) => updateFilter("status", value)}
        />
        {filtered && (
          <button
            type="button"
            className={styles.resetFilters}
            onClick={() =>
              setSearchParams(
                scope === "archived" ? { scope: "archived" } : {},
                { replace: true },
              )
            }
          >
            reset
          </button>
        )}
        {Boolean(cases?.length) && (
          <a
            className={`${styles.resetFilters} ${styles.exportFilters}`}
            href={queueExportUrl({
              query,
              scope,
              status: getStatusFilter(status),
            })}
            download
          >
            export evidence
          </a>
        )}
        <div className={styles.queueLinks}>
          <Link
            className={styles.scopeLink}
            to="/reviews/settings"
            state={{ returnTo: `/reviews${rowSearch ? `?${rowSearch}` : ""}` }}
          >
            queue settings
          </Link>
          <Link
            className={styles.scopeLink}
            to={scope === "active" ? "/reviews?scope=archived" : "/reviews"}
          >
            {scope === "active" ? "view archived" : "back to active"}
          </Link>
        </div>
      </div>

      <p className={styles.srOnly} role="status">
        {loading || !cases ? "" : `${cases.length} cases`}
      </p>

      {error ? (
        <p className={styles.pageState} role="alert">
          The review queue could not be loaded.
        </p>
      ) : cases === null ? null : cases.length === 0 ? (
        <p className={styles.pageState}>
          {anyCasesExist
            ? "No reviews match the current filters"
            : scope === "archived"
              ? "No archived reviews"
              : "No reviews left"}
        </p>
      ) : (
        <>
          <QueueTable
            cases={orderCases(cases)}
            loading={loading}
            stale={stale}
            rowSearch={rowSearch}
            sort={sort}
            direction={direction}
            onSort={applySort}
          />
          {status === "all" &&
            cases.some((reviewCase) => reviewCase.status === "deferred") && (
              <p className={styles.tableFooter}>deferred at the end</p>
            )}
        </>
      )}
    </section>
  );
}
