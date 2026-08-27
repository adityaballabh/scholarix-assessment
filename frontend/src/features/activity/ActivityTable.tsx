import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { ActivityEvent } from "../../api/types";
import Hint from "../../components/Hint";
import SortHeader from "../../components/SortHeader";
import type { SortDirection } from "../../components/SortHeader";
import { formatEventTime } from "../../lib/datetime";
import { statusText } from "../../lib/decisions";
import styles from "./ActivityPage.module.css";

export type ActivitySort = "time" | "author" | "reviewer";

export default function ActivityTable({
  events,
  sort,
  direction,
  revealNotes,
  onSort,
}: {
  events: ActivityEvent[];
  sort: ActivitySort | null;
  direction: SortDirection;
  revealNotes: boolean;
  onSort: (column: ActivitySort, direction: SortDirection | null) => void;
}) {
  const sortState = (column: ActivitySort) =>
    sort === column
      ? direction === "asc"
        ? "ascending"
        : "descending"
      : "none";

  return (
    <div role="table" aria-label="Recorded decisions" className={styles.table}>
      <div role="rowgroup">
        <div role="row" className={`${styles.row} ${styles.head}`}>
          <span role="columnheader">
            <span className={styles.srOnly}>position</span>
          </span>
          <span role="columnheader" aria-sort={sortState("author")}>
            <SortHeader
              label="author"
              active={sort === "author"}
              direction={direction}
              clearable
              onSort={(next) => onSort("author", next)}
            />
          </span>
          <span role="columnheader">case</span>
          <span role="columnheader" className={styles.actionHeader}>
            action
            <Hint text="Matching from and to values mean a note was added without changing the state" />
          </span>
          <span role="columnheader" aria-sort={sortState("reviewer")}>
            <SortHeader
              label="reviewer"
              active={sort === "reviewer"}
              direction={direction}
              clearable
              onSort={(next) => onSort("reviewer", next)}
            />
          </span>
          <span role="columnheader" aria-sort={sortState("time")}>
            <SortHeader
              label="time"
              active={sort === "time"}
              direction={direction}
              clearable
              onSort={(next) => onSort("time", next)}
            >
              when
            </SortHeader>
          </span>
          <span role="columnheader">note</span>
        </div>
      </div>

      <div role="rowgroup">
        {events.map((event, index) => (
          <div role="row" className={styles.row} key={event.id}>
            <span role="cell" className={styles.position}>
              {index + 1}
            </span>
            <span role="cell" className={styles.author} title="">
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
              {event.note && <Note text={event.note} revealed={revealNotes} />}
            </span>
          </div>
        ))}
      </div>
    </div>
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
        title=""
        onClick={() => setOpen((current) => !current)}
      >
        {text}
      </button>
    </span>
  );
}
