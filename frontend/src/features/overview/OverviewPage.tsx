import { type ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getOverview, listActivity, listCases } from "../../api/client";
import type {
  ActivityEvent,
  ReviewOverview,
  SourceHealthState,
  ValidationCase,
} from "../../api/types";
import Hint from "../../components/Hint";
import SectionRule from "../../components/SectionRule";
import {
  compactRelativeParts,
  formatEventTime,
  formatFetchedAt,
} from "../../lib/datetime";
import { actionLabels } from "../../lib/decisions";
import { CANDIDATES_HINT, SCORE_HINT, SHARE_HINT } from "../../lib/hints";
import { sourceLabel } from "../../lib/sources";
import styles from "./OverviewPage.module.css";

const sourceStateLabels: Record<SourceHealthState, string> = {
  available: "available",
  partially_available: "partially available",
  unavailable: "unavailable",
};

const ACTIVITY_PREVIEW = 4;

export default function OverviewPage() {
  const [overview, setOverview] = useState<ReviewOverview | null>(null);
  const [cases, setCases] = useState<ValidationCase[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[] | null>(null);
  const [overviewError, setOverviewError] = useState(false);
  const [casesError, setCasesError] = useState(false);
  const [activityError, setActivityError] = useState(false);
  const [overviewAttempt, setOverviewAttempt] = useState(0);
  const [casesAttempt, setCasesAttempt] = useState(0);
  const [activityAttempt, setActivityAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setOverviewError(false);
    getOverview()
      .then((result) => {
        if (active) setOverview(result);
      })
      .catch(() => {
        if (active) setOverviewError(true);
      });
    return () => {
      active = false;
    };
  }, [overviewAttempt]);

  useEffect(() => {
    let active = true;
    setCasesError(false);
    listCases({ status: "pending" })
      .then((result) => {
        if (active) setCases(result);
      })
      .catch(() => {
        if (active) setCasesError(true);
      });
    return () => {
      active = false;
    };
  }, [casesAttempt]);

  useEffect(() => {
    let active = true;
    setActivityError(false);
    listActivity()
      .then((result) => {
        if (active) setActivity(result);
      })
      .catch(() => {
        if (active) setActivityError(true);
      });
    return () => {
      active = false;
    };
  }, [activityAttempt]);

  if (overviewError)
    return (
      <p className={styles.pageState} role="alert">
        Could not load the overview{" "}
        <button
          type="button"
          onClick={() => setOverviewAttempt((attempt) => attempt + 1)}
        >
          retry overview
        </button>
      </p>
    );

  const loading = overview === null;
  const loadingPlaceholder = "—";
  const sources = overview?.sources ?? [];

  return (
    <div className={styles.sections}>
      <SectionRule label="Review Queue" />
      <div className={styles.summaryStrip}>
        <Stat
          value={
            loading
              ? loadingPlaceholder
              : overview.total_authors.toLocaleString()
          }
          label="profiles assessed"
        />
        <Stat
          value={
            loading
              ? loadingPlaceholder
              : overview.flagged_authors.toLocaleString()
          }
          label="flagged"
        />
        <Stat
          value={
            loading
              ? loadingPlaceholder
              : overview.affected_publications.toLocaleString()
          }
          label={`of ${loading ? loadingPlaceholder : overview.total_publications.toLocaleString()} publications affected`}
        />
        <Stat
          value={<CompactAge iso={overview?.queue_updated_at ?? null} />}
          label={
            <>
              since last queue update
              <Hint
                text="This time resets after a full fetch, case evidence fetch, or queue rebuild"
                align="end"
              />
            </>
          }
        />
      </div>

      <SectionRule
        label="Pending Cases"
        hint={
          <Link to="/reviews" className={styles.headerLink}>
            see all pending
          </Link>
        }
      />
      {casesError && (
        <p className={styles.pageState} role="alert">
          Could not load pending cases{" "}
          <button
            type="button"
            onClick={() => setCasesAttempt((attempt) => attempt + 1)}
          >
            retry pending cases
          </button>
        </p>
      )}
      <div className={styles.caseList}>
        <table role="table" className={styles.table}>
          <thead role="rowgroup" className={styles.caseHead}>
            <tr role="row">
              <th role="columnheader" scope="col">
                <span className={styles.srOnly}>position</span>
              </th>
              <th role="columnheader" scope="col">
                author
              </th>
              <th role="columnheader" scope="col" className={styles.hintHeader}>
                score
                <Hint text={SCORE_HINT} />
              </th>
              <th role="columnheader" scope="col" className={styles.hintHeader}>
                top share
                <Hint text={SHARE_HINT} />
              </th>
              <th role="columnheader" scope="col" className={styles.hintHeader}>
                candidates
                <Hint text={CANDIDATES_HINT} />
              </th>
              <th role="columnheader" scope="col">
                publications
              </th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {cases.map((reviewCase, index) => (
              <CaseRow
                key={reviewCase.id}
                reviewCase={reviewCase}
                position={index + 1}
              />
            ))}
          </tbody>
        </table>
      </div>

      <SectionRule label="Source Health" />
      <div className={styles.sourceList}>
        <table role="table" className={styles.table}>
          <thead role="rowgroup" className={styles.sourceHead}>
            <tr role="row">
              <th role="columnheader" scope="col">
                <span className={styles.srOnly}>position</span>
              </th>
              <th role="columnheader" scope="col">
                source
              </th>
              <th role="columnheader" scope="col">
                status
              </th>
              <th role="columnheader" scope="col">
                details
              </th>
              <th role="columnheader" scope="col">
                fetched
              </th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {sources.map((source, index) => (
              <tr role="row" className={styles.sourceRow} key={source.source}>
                <td role="cell" className={styles.position}>
                  {index + 1}
                </td>
                <th role="rowheader" scope="row" className={styles.sourceName}>
                  {sourceLabel(source.source)}
                </th>
                <td
                  role="cell"
                  className={`${styles.sourceState} ${source.state === "partially_available" ? styles.partialSource : ""} ${source.state === "unavailable" ? styles.unavailableSource : ""}`}
                >
                  {sourceStateLabels[source.state]}
                </td>
                <td role="cell" className={styles.sourceNoteCell}>
                  <SourceNote note={source.note} />
                </td>
                <td role="cell" className={styles.sourceFetched}>
                  <time dateTime={source.fetched_at ?? undefined}>
                    {formatFetchedAt(source.fetched_at) ?? "never"}
                  </time>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionRule
        label="Recent Activity"
        hint={
          <Link to="/activity" className={styles.headerLink}>
            see all activity
          </Link>
        }
      />
      {activityError ? (
        <p className={styles.pageState} role="alert">
          Could not load recent activity{" "}
          <button
            type="button"
            onClick={() => setActivityAttempt((attempt) => attempt + 1)}
          >
            retry recent activity
          </button>
        </p>
      ) : activity === null ? null : activity.length === 0 ? (
        <p className={styles.emptyState}>No activity yet</p>
      ) : (
        <div className={styles.activityList}>
          <table role="table" className={styles.table}>
            <thead role="rowgroup" className={styles.activityHead}>
              <tr role="row">
                <th role="columnheader" scope="col">
                  <span className={styles.srOnly}>position</span>
                </th>
                <th role="columnheader" scope="col">
                  author
                </th>
                <th role="columnheader" scope="col">
                  action
                </th>
                <th role="columnheader" scope="col">
                  reviewer
                </th>
                <th role="columnheader" scope="col">
                  when
                </th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {activity.slice(0, ACTIVITY_PREVIEW).map((event, index) => (
                <tr role="row" className={styles.activityRow} key={event.id}>
                  <td role="cell" className={styles.position}>
                    {index + 1}
                  </td>
                  <th
                    role="rowheader"
                    scope="row"
                    className={styles.activityTarget}
                  >
                    {event.target_name}
                  </th>
                  <td role="cell" className={styles.activityAction}>
                    {actionLabels[event.action_type]}
                  </td>
                  <td role="cell" className={styles.activityActor}>
                    {event.actor}
                  </td>
                  <td role="cell" className={styles.activityTime}>
                    {formatEventTime(event.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {activity.length > ACTIVITY_PREVIEW && (
            <p className={styles.emptyState}>
              <Link to="/activity" className={styles.emptyStateLink}>
                full history
              </Link>
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function SourceNote({ note }: { note: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [clipped, setClipped] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setClipped(element.scrollWidth > element.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [note]);

  return (
    <span
      className={styles.sourceNoteWrap}
      data-hint={clipped ? note : undefined}
    >
      {/* An empty title suppresses Safari's automatic tooltip on truncated text */}
      <span ref={ref} className={styles.sourceNote} title="">
        {note}
      </span>
    </span>
  );
}

function CompactAge({ iso }: { iso: string | null }) {
  const { value, unit } = compactRelativeParts(iso);
  return (
    <>
      {value}
      {unit ? <span className={styles.statUnit}>{unit}</span> : null}
    </>
  );
}

function Stat({ value, label }: { value: ReactNode; label: ReactNode }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}

function CaseRow({
  reviewCase,
  position,
}: {
  reviewCase: ValidationCase;
  position: number;
}) {
  return (
    <tr role="row" className={styles.caseRow}>
      <td role="cell" className={styles.position}>
        {position}
      </td>
      <th role="rowheader" scope="row" className={styles.caseName}>
        <Link to={`/reviews/${reviewCase.id}`} className={styles.caseLink}>
          {reviewCase.target.author_name}
        </Link>
      </th>
      <td role="cell" className={styles.score}>
        {Math.round(reviewCase.priority_score)}
      </td>
      <td role="cell" className={styles.topShare}>
        {reviewCase.detail.top_share === null
          ? "—"
          : `${Math.round(reviewCase.detail.top_share)}%`}
      </td>
      <td role="cell" className={styles.candidateCount}>
        {reviewCase.detail.candidate_ids.length}
      </td>
      <td role="cell" className={styles.affectedCount}>
        {reviewCase.affected_count}
      </td>
    </tr>
  );
}
