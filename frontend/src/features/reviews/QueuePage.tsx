import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listCases, queueExportUrl } from "../../api/client";
import Hint from "../../components/Hint";
import { CANDIDATES_HINT, SCORE_HINT, SHARE_HINT } from "../../lib/hints";
import Select from "../../components/Select";
import SortHeader from "../../components/SortHeader";
import type { SortDirection } from "../../components/SortHeader";
import type { ValidationCase } from "../../api/types";
import {
  defaultStatusForScope,
  getStatusFilter,
  readOption,
  readQueueScope,
  statusOptions,
  statusOrder,
} from "./filters";
import styles from "./QueuePage.module.css";

type SortColumn = "score" | "share" | "candidates" | "publications" | "status";

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
  const sort: SortColumn | "" =
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
            <th role="columnheader" scope="col" className={styles.hintHeader}>
              <SortHeader
                label="score"
                active={sort === "score"}
                direction={direction}
                clearable
                onSort={(next) => onSort("score", next)}
              />
              <Hint text={SCORE_HINT} />
            </th>
            <th role="columnheader" scope="col" className={styles.hintHeader}>
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
            <th role="columnheader" scope="col" className={styles.hintHeader}>
              <SortHeader
                label="candidates"
                active={sort === "candidates"}
                direction={direction}
                clearable
                onSort={(next) => onSort("candidates", next)}
              />
              <Hint text={CANDIDATES_HINT} />
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
      <th role="rowheader" scope="row" className={styles.author} title="">
        <Link
          to={{ pathname: `/reviews/${reviewCase.id}`, search }}
          className={styles.reviewLink}
        >
          {reviewCase.target.author_name}
        </Link>
      </th>
      <td role="cell" className={styles.score}>
        {Math.round(reviewCase.priority_score)}
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
