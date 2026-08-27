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
} from "./filters";
import QueueTable from "./QueueTable";
import { orderCases, readQueueSort, type QueueSortColumn } from "./ordering";
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
  const [loadAttempt, setLoadAttempt] = useState(0);

  const query = searchParams.get("query") ?? "";
  const rawStatus = searchParams.get("status");
  const rawScope = searchParams.get("scope");
  const scope = readQueueScope(rawScope);
  const defaultStatus = defaultStatusForScope(scope);
  const status = readOption(rawStatus, statusOptions, defaultStatus);
  const caseLinkSearch = searchParams.toString();
  const rawSort = searchParams.get("sort");
  const rawDirection = searchParams.get("dir");
  const { column: sort, direction } = readQueueSort(searchParams);

  const [draftQuery, setDraftQuery] = useState(query);

  useEffect(() => {
    let active = true;

    listCases({ scope })
      .then((allCases) => {
        if (active) setAnyCasesExist(allCases.length > 0);
      })
      .catch(() => {
        // The filtered request reports load errors
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
    const invalid: string[] = [];
    if (rawStatus !== null && rawStatus !== status) invalid.push("status");
    if (rawScope !== null && rawScope !== scope) invalid.push("scope");
    if (rawSort !== null && rawSort !== sort) invalid.push("sort");
    if (rawDirection !== null && (!sort || rawDirection !== "asc"))
      invalid.push("dir");
    if (invalid.length === 0) return;

    setSearchParams(
      (previous) => {
        const nextParams = new URLSearchParams(previous);
        invalid.forEach((name) => nextParams.delete(name));
        return nextParams;
      },
      { replace: true },
    );
  }, [
    rawStatus,
    rawScope,
    scope,
    status,
    rawSort,
    sort,
    rawDirection,
    setSearchParams,
  ]);

  useEffect(() => {
    setDraftQuery(query);
  }, [query]);

  useEffect(() => {
    if (draftQuery === query) return;

    const timer = setTimeout(
      () =>
        setSearchParams(
          (previous) => {
            const next = new URLSearchParams(previous);
            if (draftQuery) next.set("query", draftQuery);
            else next.delete("query");
            return next;
          },
          { replace: true },
        ),
      SEARCH_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [draftQuery, query, setSearchParams]);

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
  }, [query, scope, status, loadAttempt]);

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

  const hasActiveFilters = Boolean(query || status !== defaultStatus);

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
        {hasActiveFilters && (
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
            state={{
              returnTo: `/reviews${caseLinkSearch ? `?${caseLinkSearch}` : ""}`,
            }}
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
          Could not load the review queue{" "}
          <button
            type="button"
            className={styles.resetFilters}
            onClick={() => setLoadAttempt((attempt) => attempt + 1)}
          >
            retry
          </button>
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
        <QueueTable
          cases={orderCases(cases, sort, direction)}
          loading={loading}
          stale={stale}
          caseLinkSearch={caseLinkSearch}
          sort={sort}
          direction={direction}
          onSort={applySort}
        />
      )}
    </section>
  );
}
