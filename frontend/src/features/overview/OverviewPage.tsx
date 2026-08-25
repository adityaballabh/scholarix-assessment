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
import styles from "./OverviewPage.module.css";

const sourceNames: Record<string, string> = {
  semantic_scholar: "Semantic Scholar",
  openalex: "OpenAlex",
  orcid: "ORCID",
  google_scholar: "Google Scholar",
  pubmed: "PubMed",
};

function sourceName(source: string) {
  return sourceNames[source] ?? source.replace(/_/g, " ");
}

const sourceStateLabels: Record<SourceHealthState, string> = {
  available: "available",
  partially_available: "partially available",
  unavailable: "unavailable",
};

const ACTIVITY_PREVIEW = 4;

interface OverviewData {
  overview: ReviewOverview;
  cases: ValidationCase[];
  activity: ActivityEvent[];
}

export default function OverviewPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;

    Promise.all([
      getOverview(),
      listCases({ status: "pending" }),
      listActivity(),
    ])
      .then(([overview, cases, activity]) => {
        if (active) setData({ overview, cases, activity });
      })
      .catch(() => {
        if (active) setError(true);
      });

    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return (
      <p className={styles.pageState} role="alert">
        The review overview could not be loaded.
      </p>
    );
  }

  // The page keeps its structure while the three requests are outstanding, so
  // section rules and table heads hold their place and only values swap in.
  const loading = data === null;
  const pending = "\u2014";
  const cases = data?.cases ?? [];
  const activity = data?.activity ?? [];
  const sources = data?.overview.sources ?? [];

  return (
    <div className={styles.sections}>
      <SectionRule label="Review Queue" />
      <div className={styles.summaryStrip}>
        <Stat
          value={loading ? pending : data.overview.total_authors.toLocaleString()}
          label="profiles assessed"
        />
        <Stat
          value={loading ? pending : data.overview.flagged_authors.toLocaleString()}
          label="flagged"
        />
        <Stat
          value={
            loading ? pending : data.overview.affected_publications.toLocaleString()
          }
          label={`of ${loading ? pending : data.overview.total_publications.toLocaleString()} publications affected`}
        />
        <Stat
          value={<CompactAge iso={data?.overview.queue_updated_at ?? null} />}
          label={
            <>
              since last queue update
              <Hint
                text="Fetching all data, changing queue settings, or fetching evidence for a specific case rebuilds the queue"
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
                  {sourceName(source.source)}
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
      {loading ? null : activity.length === 0 ? (
        <p className={styles.emptyState}>
          No{" "}
          <Link to="/activity" className={styles.emptyStateLink}>
            activity
          </Link>{" "}
          yet
        </p>
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
      {/* Safari shows its own tooltip over any ellipsis-truncated text, with no
          title attribute involved. An empty title is what suppresses it. */}
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
