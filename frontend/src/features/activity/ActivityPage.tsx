import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getOverview, listActivity } from "../../api/client";
import type { ActivityEvent, ReviewStatus } from "../../api/types";
import Select from "../../components/Select";
import type { SelectOption } from "../../components/Select";
import type { SortDirection } from "../../components/SortHeader";
import { matchesAuthorName, matchesNote } from "../../lib/search";
import { updateSortParams } from "../../lib/sortParams";
import ActivityTable from "./ActivityTable";
import type { ActivitySort } from "./ActivityTable";
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

type SinceFilter = "" | "1h" | "24h" | "7d" | "30d" | "run";

const sinceOptions: SelectOption<SinceFilter>[] = [
  { value: "", label: "any time" },
  { value: "run", label: "since the last queue update" },
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
  const [queueUpdatedAt, setQueueUpdatedAt] = useState<string | null>(null);
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
        if (active) setQueueUpdatedAt(overview.queue_updated_at);
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
      ? (queueUpdatedAt && new Date(queueUpdatedAt).getTime()) || null
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
    setSearchParams((previous) => updateSortParams(previous, column, next), {
      replace: true,
    });
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

      {!events || runFilterLoading ? null : runFilterUnavailable ? (
        <p className={styles.pageState} role="alert">
          The last queue update time could not be loaded.
        </p>
      ) : ordered.length === 0 ? (
        <p className={styles.pageState}>
          {events.length === 0
            ? "No decisions recorded yet"
            : "No activity matches the current filters"}
        </p>
      ) : (
        <ActivityTable
          events={ordered}
          sort={explicitSort}
          direction={direction}
          revealNotes={noteQuery !== ""}
          onSort={applySort}
        />
      )}
    </section>
  );
}
