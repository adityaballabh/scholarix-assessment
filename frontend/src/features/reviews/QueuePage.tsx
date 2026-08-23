import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listCases } from "../../api/client";
import Hint from "../../components/Hint";
import Select from "../../components/Select";
import SortHeader from "../../components/SortHeader";
import type { SortDirection } from "../../components/SortHeader";
import type { ValidationCase } from "../../api/types";
import {
  defaultStatusForScope,
  getStatusFilter,
  priorityOptions,
  readOption,
  readQueueScope,
  statusOptions,
  statusOrder,
} from "./filters";
import styles from "./QueuePage.module.css";

type SortColumn = "share" | "publications" | "status";

const STALE_DELAY_MS = 500;

const SHARE_HINT =
  "highest share of publications across all S2 IDs for an author";

export default function QueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [cases, setCases] = useState<ValidationCase[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [anyCasesExist, setAnyCasesExist] = useState(true);
  const [stale, setStale] = useState(false);

  const query = searchParams.get("query") ?? "";
  const rawPriority = searchParams.get("priority");
  const rawStatus = searchParams.get("status");
  const rawScope = searchParams.get("scope");
  const scope = readQueueScope(rawScope);
  const defaultStatus = defaultStatusForScope(scope);
  const priority = readOption(rawPriority, priorityOptions, "");
  const status = readOption(rawStatus, statusOptions, defaultStatus);
  const rowSearch = searchParams.toString();
  const rawSort = searchParams.get("sort");
  const sort: SortColumn | "" =
    rawSort === "publications" || rawSort === "share" || rawSort === "status"
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
      .catch(() => {});

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
      rawPriority !== null && rawPriority !== priority ? "priority" : null,
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
  }, [rawStatus, rawPriority, rawScope, scope, status, priority]);

  useEffect(() => {
    setDraftQuery(query);
  }, [query]);

  useEffect(() => {
    if (draftQuery === query) return;

    const timer = setTimeout(() => updateFilter("query", draftQuery), 200);
    return () => clearTimeout(timer);
  }, [draftQuery]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);

    listCases({
      query: query || undefined,
      priority: priority || undefined,
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
  }, [priority, query, scope, status]);

  function orderCases(rows: ValidationCase[]): ValidationCase[] {
    if (!sort) return rows;

    return [...rows].sort((a, b) => {
      const gap =
        sort === "share"
          ? (a.detail.top_share ?? 0) - (b.detail.top_share ?? 0)
          : sort === "status"
            ? statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status)
            : a.affected_count - b.affected_count;
      return direction === "asc" ? gap : -gap;
    });
  }

  function applySort(column: SortColumn, next: SortDirection | null) {
    setSearchParams(
      (previous) => {
        const params = new URLSearchParams(previous);
        params.delete("dir");

        if (next === null) {
          params.delete("sort");
          return params;
        }

        params.set("sort", column);
        if (next === "asc") params.set("dir", "asc");
        return params;
      },
      { replace: true },
    );
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

  const filtered = Boolean(query || priority || status !== defaultStatus);

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
        <Select
          label="Priority"
          value={priority}
          options={priorityOptions}
          onChange={(value) => updateFilter("priority", value)}
        />
        <Link
          className={styles.scopeLink}
          to={scope === "active" ? "/reviews?scope=archived" : "/reviews"}
        >
          {scope === "active" ? "view archived" : "back to active"}
        </Link>
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
      </div>

      <p className={styles.srOnly} role="status">
        {loading || !cases ? "" : `${cases.length} cases`}
      </p>

      {error ? (
        <p className={styles.pageState} role="alert">
          The review queue could not be loaded.
        </p>
      ) : cases === null ? (
        <p className={styles.pageState}>Loading reviews…</p>
      ) : cases.length === 0 ? (
        <p className={styles.pageState}>
          {anyCasesExist
            ? "No reviews match the current filters"
            : scope === "archived"
              ? "No archived reviews"
              : "No reviews left"}
        </p>
      ) : (
        <>
          <ReviewTable
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

function ReviewTable({
  cases,
  loading,
  stale,
  rowSearch,
  sort,
  direction,
  onSort,
}: {
  cases: ValidationCase[];
  loading: boolean;
  stale: boolean;
  rowSearch: string;
  sort: string;
  direction: SortDirection;
  onSort: (column: SortColumn, next: SortDirection | null) => void;
}) {
  return (
    <div className={styles.tableScroll}>
      <table
        role="table"
        aria-busy={loading}
        className={`${styles.table} ${stale ? styles.stale : ""}`}
      >
        <thead role="rowgroup">
          <tr role="row" className={styles.headerRow}>
            <th role="columnheader" scope="col">
              <span className={styles.srOnly}>position</span>
            </th>
            <th role="columnheader" scope="col">
              author
            </th>
            <th role="columnheader" scope="col">
              priority
            </th>
            <th role="columnheader" scope="col" className={styles.shareHeader}>
              <SortHeader
                label="top share"
                active={sort === "share"}
                direction={direction}
                clearable
                onSort={(next) => onSort("share", next)}
              >
                top share
              </SortHeader>
              <Hint text={SHARE_HINT} />
            </th>
            <th role="columnheader" scope="col">
              candidates
            </th>
            <th role="columnheader" scope="col">
              <SortHeader
                label="publications"
                active={sort === "publications"}
                direction={direction}
                clearable
                onSort={(next) => onSort("publications", next)}
              />
            </th>
            <th role="columnheader" scope="col">
              <SortHeader
                label="status"
                active={sort === "status"}
                direction={direction}
                clearable
                onSort={(next) => onSort("status", next)}
              />
            </th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {cases.map((reviewCase, index) => (
            <ReviewRow
              key={reviewCase.id}
              reviewCase={reviewCase}
              position={index + 1}
              search={rowSearch}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewRow({
  reviewCase,
  position,
  search,
}: {
  reviewCase: ValidationCase;
  position: number;
  search: string;
}) {
  return (
    <tr role="row" className={styles.reviewRow}>
      <td role="cell" className={styles.position}>
        {position}
      </td>
      <th role="rowheader" scope="row" className={styles.author}>
        <Link
          to={{ pathname: `/reviews/${reviewCase.id}`, search }}
          className={styles.reviewLink}
        >
          {reviewCase.target.author_name}
        </Link>
      </th>
      <td role="cell" className={styles.priority}>
        {reviewCase.priority.replace(/_/g, " ")}
      </td>
      <td role="cell" className={styles.numericValue}>
        {reviewCase.detail.top_share === null
          ? "—"
          : `${Math.round(reviewCase.detail.top_share)}%`}
      </td>
      <td role="cell" className={styles.numericValue}>
        {reviewCase.detail.candidate_ids.length}
      </td>
      <td role="cell" className={styles.numericValue}>
        {reviewCase.affected_count}
      </td>
      <td role="cell" className={styles.status}>
        {reviewCase.status.replace(/_/g, " ")}
      </td>
    </tr>
  );
}
