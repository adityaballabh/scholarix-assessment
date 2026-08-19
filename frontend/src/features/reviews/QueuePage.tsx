import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { OPEN_STATUSES, listCases } from "../../api/client";
import Select from "../../components/Select";
import type { SelectOption } from "../../components/Select";
import type {
  CasePriority,
  CaseQueryFilters,
  ReviewStatus,
  ValidationCase,
} from "../../api/types";
import styles from "./QueuePage.module.css";

const priorityOptions: SelectOption<CasePriority | "">[] = [
  { value: "", label: "all priorities" },
  { value: "high", label: "high" },
  { value: "medium", label: "medium" },
  { value: "low", label: "low" },
];

const statusOptions: SelectOption<ReviewStatus | "open" | "all">[] = [
  { value: "all", label: "all states" },
  { value: "open", label: "open" },
  { value: "pending", label: "pending" },
  { value: "in_review", label: "in review" },
  { value: "deferred", label: "deferred" },
  { value: "reopened", label: "reopened" },
  { value: "resolved", label: "resolved" },
];

const STALE_DELAY_MS = 500;

const SHARE_HINT =
  "highest share of publications across all S2 IDs for an author";

function readOption<T extends string>(
  raw: string | null,
  options: SelectOption<T>[],
  fallback: T,
): T {
  return options.some((option) => option.value === raw) ? (raw as T) : fallback;
}

function getStatusFilter(status: string): CaseQueryFilters["status"] {
  if (status === "all") return undefined;
  if (status === "open") return OPEN_STATUSES;
  return status as ReviewStatus;
}

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
  const priority = readOption(rawPriority, priorityOptions, "");
  const status = readOption(rawStatus, statusOptions, "open");

  const [draftQuery, setDraftQuery] = useState(query);

  useEffect(() => {
    let active = true;

    listCases()
      .then((allCases) => {
        if (active) setAnyCasesExist(allCases.length > 0);
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, []);

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
  }, [rawStatus, rawPriority]);

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
  }, [priority, query, status]);

  function updateFilter(name: string, value: string) {
    setSearchParams(
      (previous) => {
        const nextParams = new URLSearchParams(previous);

        if (value && !(name === "status" && value === "open")) {
          nextParams.set(name, value);
        } else {
          nextParams.delete(name);
        }

        return nextParams;
      },
      { replace: true },
    );
  }

  const filtered = Boolean(query || priority || status !== "open");

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
        {filtered && (
          <button
            type="button"
            className={styles.resetFilters}
            onClick={() => setSearchParams({}, { replace: true })}
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
            ? "No reviews match the current filters."
            : "No reviews left."}
        </p>
      ) : (
        <>
          <ReviewTable cases={cases} loading={loading} stale={stale} />
          <p className={styles.tableFooter}>deferred at the end</p>
        </>
      )}
    </section>
  );
}

function ReviewTable({
  cases,
  loading,
  stale,
}: {
  cases: ValidationCase[];
  loading: boolean;
  stale: boolean;
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
            <th role="columnheader" scope="col">author</th>
            <th role="columnheader" scope="col" className={styles.shareHeader}>
              top share
              <button
                type="button"
                className={styles.hint}
                aria-label={SHARE_HINT}
              >
                <span aria-hidden="true" className={styles.hintMark}>
                  i
                </span>
                <span aria-hidden="true" className={styles.hintText}>
                  {SHARE_HINT}
                </span>
              </button>
            </th>
            <th role="columnheader" scope="col">candidates</th>
            <th role="columnheader" scope="col">publications</th>
            <th role="columnheader" scope="col">priority</th>
            <th role="columnheader" scope="col">status</th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {cases.map((reviewCase, index) => (
            <ReviewRow
              key={reviewCase.id}
              reviewCase={reviewCase}
              position={index + 1}
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
}: {
  reviewCase: ValidationCase;
  position: number;
}) {
  return (
    <tr role="row" className={styles.reviewRow}>
      <td role="cell" className={styles.position}>{position}</td>
      <th role="rowheader" scope="row" className={styles.author}>
        <Link to={`/reviews/${reviewCase.id}`} className={styles.reviewLink}>
          {reviewCase.target.author_name}
        </Link>
      </th>
      <td role="cell" className={styles.numericValue}>
        {reviewCase.detail.top_share === null
          ? "—"
          : `${Math.round(reviewCase.detail.top_share)}%`}
      </td>
      <td role="cell" className={styles.numericValue}>
        {reviewCase.detail.candidate_ids.length}
      </td>
      <td role="cell" className={styles.numericValue}>{reviewCase.affected_count}</td>
      <td role="cell" className={styles.priority}>{reviewCase.priority}</td>
      <td role="cell" className={styles.status}>
        {reviewCase.status.replace(/_/g, " ")}
      </td>
    </tr>
  );
}
