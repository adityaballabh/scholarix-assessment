import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getOverview, listActivity } from "../../api/client";
import type { ActivityEvent, ReviewStatus } from "../../api/types";
import Hint from "../../components/Hint";
import Select from "../../components/Select";
import type { SelectOption } from "../../components/Select";
import SortHeader from "../../components/SortHeader";
import type { SortDirection } from "../../components/SortHeader";
import { formatEventTime } from "../../lib/datetime";
import { statusText } from "../../lib/decisions";
import { matchesAuthorName, matchesNote } from "../../lib/search";
import styles from "./ActivityPage.module.css";

type SideFilter = ReviewStatus | "";

const sideOptions: SelectOption<SideFilter>[] = [
  { value: "", label: "any" },
  { value: "pending", label: "pending" },
  { value: "one_author", label: "one author" },
  { value: "needs_split", label: "needs split" },
  { value: "uncertain", label: "uncertain" },
  { value: "deferred", label: "deferred" },
];

type ActivitySort = "time" | "author" | "reviewer";

type SinceFilter = "" | "1h" | "24h" | "7d" | "30d" | "run";

const sinceOptions: SelectOption<SinceFilter>[] = [
  { value: "", label: "any time" },
  { value: "run", label: "since the last audit" },
  { value: "1h", label: "last hour" },
  { value: "24h", label: "last 24 hours" },
  { value: "7d", label: "last 7 days" },
  { value: "30d", label: "last 30 days" },
];

const sinceWindows: Record<Exclude<SinceFilter, "" | "run">, number> = {
  "1h": 3600_000,
  "24h": 86_400_000,
  "7d": 7 * 86_400_000,
  "30d": 30 * 86_400_000,
};

function readSince(raw: string | null): SinceFilter {
  return sinceOptions.some((option) => option.value === raw)
    ? (raw as SinceFilter)
    : "";
}

function readSide(raw: string | null): SideFilter {
  return sideOptions.some((option) => option.value === raw)
    ? (raw as SideFilter)
    : "";
}

export default function ActivityPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [events, setEvents] = useState<ActivityEvent[] | null>(null);
  const [auditedAt, setAuditedAt] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [overviewError, setOverviewError] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(true);

  const from = readSide(searchParams.get("from"));
  const to = readSide(searchParams.get("to"));
  const reviewer = searchParams.get("reviewer") ?? "";
  const query = searchParams.get("query") ?? "";
  const since = readSince(searchParams.get("since"));
  const noteQuery = searchParams.get("note") ?? "";
  const rawSort = searchParams.get("sort");
  const explicitSort: ActivitySort | null =
    rawSort === "author" || rawSort === "reviewer" || rawSort === "time"
      ? rawSort
      : null;
  const sort: ActivitySort = explicitSort ?? "time";
  const direction: SortDirection =
    searchParams.get("dir") === "asc" ? "asc" : "desc";

  useEffect(() => {
    let active = true;
    listActivity()
      .then((found) => {
        if (active) setEvents(found);
      })
      .catch(() => {
        if (active) setError(true);
      });
    getOverview()
      .then((overview) => {
        if (active) setAuditedAt(overview.audited_at);
      })
      .catch(() => {
        if (active) setOverviewError(true);
      })
      .finally(() => {
        if (active) setOverviewLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const reviewerOptions = useMemo<SelectOption<string>[]>(() => {
    const actors = [
      ...new Set((events ?? []).map((event) => event.actor)),
    ].sort();
    return [
      { value: "", label: "all reviewers" },
      ...actors.map((actor) => ({ value: actor, label: actor })),
    ];
  }, [events]);

  const filtered = Boolean(
    query ||
      noteQuery ||
      from ||
      to ||
      reviewer ||
      since ||
      explicitSort !== null,
  );

  const cutoff = !since
    ? null
    : since === "run"
      ? (auditedAt && new Date(auditedAt).getTime()) || null
      : Date.now() - sinceWindows[since];
  const runFilterUnavailable = since === "run" && overviewError;
  const runFilterLoading = since === "run" && overviewLoading;

  const visible = (events ?? []).filter(
    (event) =>
      (!from || event.before === from) &&
      (!to || event.after === to) &&
      (!reviewer || event.actor === reviewer) &&
      (!query || matchesAuthorName(event.target_name, query)) &&
      (!noteQuery ||
        (event.note !== null && matchesNote(event.note, noteQuery))) &&
      (cutoff === null || new Date(event.created_at).getTime() >= cutoff),
  );

  const ordered = [...visible].sort((a, b) => {
    const gap =
      sort === "author"
        ? a.target_name.localeCompare(b.target_name)
        : sort === "reviewer"
          ? a.actor.localeCompare(b.actor)
          : Date.parse(a.created_at) - Date.parse(b.created_at);
    return direction === "asc" ? gap : -gap;
  });

  function applySort(column: ActivitySort, next: SortDirection | null) {
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
        const next = new URLSearchParams(previous);
        if (value) next.set(name, value);
        else next.delete(name);
        return next;
      },
      { replace: true },
    );
  }

  if (error) {
    return (
      <p className={styles.pageState} role="alert">
        Activity could not be loaded.
      </p>
    );
  }

  if (!events) return <p className={styles.pageState}>Loading activity…</p>;

  return (
    <section className={styles.page}>
      <div className={styles.filters}>
        <label className={styles.searchLabel}>
          <span className={styles.srOnly}>search author</span>
          <input
            type="search"
            className={styles.search}
            value={query}
            placeholder="search author"
            onChange={(event) => updateFilter("query", event.target.value)}
          />
        </label>
        <label className={styles.searchLabel}>
          <span className={styles.srOnly}>search notes</span>
          <input
            type="search"
            className={styles.search}
            value={noteQuery}
            placeholder="search notes"
            onChange={(event) => updateFilter("note", event.target.value)}
          />
        </label>
        <Select
          label="from state"
          prefix="from"
          value={from}
          options={sideOptions}
          onChange={(value) => updateFilter("from", value)}
        />
        <Select
          label="to state"
          prefix="to"
          value={to}
          options={sideOptions}
          onChange={(value) => updateFilter("to", value)}
        />
        <Select
          label="reviewer"
          value={reviewer}
          options={reviewerOptions}
          onChange={(value) => updateFilter("reviewer", value)}
        />
        <Select
          label="when"
          value={since}
          options={sinceOptions}
          onChange={(value) => updateFilter("since", value)}
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

      {runFilterLoading ? (
        <p className={styles.pageState}>Loading the last audit time…</p>
      ) : runFilterUnavailable ? (
        <p className={styles.pageState} role="alert">
          The last audit time could not be loaded.
        </p>
      ) : ordered.length === 0 ? (
        <p className={styles.pageState}>
          {events.length === 0
            ? "No decisions recorded yet"
            : "No activity matches the current filters"}
        </p>
      ) : (
        <div
          role="table"
          aria-label="Recorded decisions"
          className={styles.table}
        >
          <div role="rowgroup">
            <div role="row" className={`${styles.row} ${styles.head}`}>
              <span role="columnheader">
                <span className={styles.srOnly}>position</span>
              </span>
              <span role="columnheader">
                <SortHeader
                  label="author"
                  active={explicitSort === "author"}
                  direction={direction}
                  clearable
                  onSort={(next) => applySort("author", next)}
                />
              </span>
              <span role="columnheader">case</span>
              <span role="columnheader" className={styles.actionHeader}>
                action
                <Hint text="Matching from and to values mean a note was added without changing the state" />
              </span>
              <span role="columnheader">
                <SortHeader
                  label="reviewer"
                  active={explicitSort === "reviewer"}
                  direction={direction}
                  clearable
                  onSort={(next) => applySort("reviewer", next)}
                />
              </span>
              <span role="columnheader">
                <SortHeader
                  label="time"
                  active={explicitSort === "time"}
                  direction={direction}
                  clearable
                  onSort={(next) => applySort("time", next)}
                >
                  when
                </SortHeader>
              </span>
              <span role="columnheader">note</span>
            </div>
          </div>

          <div role="rowgroup">
            {ordered.map((event, index) => (
              <div role="row" className={styles.row} key={event.id}>
                <span role="cell" className={styles.position}>
                  {index + 1}
                </span>
                <span role="cell" className={styles.author}>
                  {event.target_name}
                </span>
                <span role="cell" className={styles.case}>
                  <Link
                    to={`/reviews/${event.case_id}`}
                    className={styles.caseLink}
                  >
                    {event.case_id.replace(/^c-/, "#")}
                  </Link>
                </span>
                <span role="cell" className={styles.transition}>
                  {statusText(event.before)} → {statusText(event.after)}
                </span>
                <span role="cell" className={styles.actor}>
                  {event.actor}
                </span>
                <span role="cell" className={styles.time}>
                  {formatEventTime(event.created_at)}
                </span>
                <span role="cell" className={styles.noteCell}>
                  {event.note && (
                    <Note text={event.note} revealed={noteQuery !== ""} />
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function Note({ text, revealed }: { text: string; revealed: boolean }) {
  const ref = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(revealed);
  const [clipped, setClipped] = useState(false);

  useEffect(() => {
    setOpen(revealed);
  }, [revealed]);

  useEffect(() => {
    const element = ref.current;
    // Only measure while collapsed, since expanded text wraps and never reports overflow
    if (!element || open) return;

    const measure = () => setClipped(element.scrollWidth > element.clientWidth);
    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text, open]);

  const interactive = clipped || open;

  return (
    <span
      className={styles.noteWrap}
      data-hint={
        interactive
          ? open
            ? "click to collapse"
            : "click to expand"
          : undefined
      }
    >
      <button
        ref={ref}
        type="button"
        disabled={!interactive}
        aria-expanded={open}
        className={`${styles.note} ${open ? styles.noteOpen : ""}`}
        onClick={() => setOpen((current) => !current)}
      >
        {text}
      </button>
    </span>
  );
}
