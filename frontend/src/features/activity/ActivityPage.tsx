import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getOverview, listActivity } from "../../api/client";
import type { ActivityEvent } from "../../api/types";
import Select from "../../components/Select";
import type { SelectOption } from "../../components/Select";
import type { SortDirection } from "../../components/SortHeader";
import { matchesAuthorName, matchesNote } from "../../lib/search";
import { updateSortParams } from "../../lib/sortParams";
import ActivityTable from "./ActivityTable";
import {
  normalizeActivitySearch,
  readActivityFilters,
  sinceOptions,
  transitionOptions,
  SINCE_WINDOWS_MS,
  type ActivitySort,
} from "./filters";
import styles from "./ActivityPage.module.css";

export default function ActivityPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [events, setEvents] = useState<ActivityEvent[] | null>(null);
  const [queueUpdatedAt, setQueueUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [overviewError, setOverviewError] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(true);

  const [activityAttempt, setActivityAttempt] = useState(0);
  const [overviewAttempt, setOverviewAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setError(false);
    listActivity()
      .then((found) => {
        if (active) setEvents(found);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [activityAttempt]);

  useEffect(() => {
    let active = true;
    setOverviewError(false);
    setOverviewLoading(true);
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
  }, [overviewAttempt]);

  const reviewers = useMemo(
    () =>
      events === null
        ? undefined
        : [...new Set(events.map((event) => event.actor))].sort(),
    [events],
  );
  const reviewerOptions: SelectOption<string>[] = [
    { value: "", label: "all reviewers" },
    ...(reviewers ?? []).map((actor) => ({ value: actor, label: actor })),
  ];
  const search = searchParams.toString();
  const normalizedSearch = normalizeActivitySearch(
    searchParams,
    reviewers,
  ).toString();
  const {
    fromStatus,
    toStatus,
    reviewer,
    query,
    noteQuery,
    since,
    explicitSort,
    sort,
    direction,
  } = readActivityFilters(new URLSearchParams(normalizedSearch));

  useEffect(() => {
    if (search !== normalizedSearch)
      setSearchParams(normalizedSearch, { replace: true });
  }, [search, normalizedSearch, setSearchParams]);

  const hasActiveFilters = Boolean(
    query ||
      noteQuery ||
      fromStatus ||
      toStatus ||
      reviewer ||
      since ||
      explicitSort !== null,
  );

  const cutoff = !since
    ? null
    : since === "run"
      ? (queueUpdatedAt && new Date(queueUpdatedAt).getTime()) || null
      : Date.now() - SINCE_WINDOWS_MS[since];
  const runFilterUnavailable = since === "run" && overviewError;
  const runFilterLoading = since === "run" && overviewLoading;

  const visible = (events ?? []).filter(
    (event) =>
      (!fromStatus || event.before === fromStatus) &&
      (!toStatus || event.after === toStatus) &&
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
        Could not load activity{" "}
        <button
          type="button"
          className={styles.resetFilters}
          onClick={() => setActivityAttempt((attempt) => attempt + 1)}
        >
          retry
        </button>
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
          value={fromStatus}
          options={transitionOptions}
          onChange={(value) => updateFilter("from", value)}
        />
        <Select
          label="to state"
          prefix="to"
          value={toStatus}
          options={transitionOptions}
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
        {hasActiveFilters && (
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
          Could not load the last queue update time{" "}
          <button
            type="button"
            className={styles.resetFilters}
            onClick={() => setOverviewAttempt((attempt) => attempt + 1)}
          >
            retry
          </button>
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
          sort={sort}
          direction={direction}
          revealNotes={noteQuery !== ""}
          onSort={applySort}
        />
      )}
    </section>
  );
}
