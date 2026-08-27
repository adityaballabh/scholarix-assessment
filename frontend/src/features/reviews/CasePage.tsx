import { useEffect, useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  ApiError,
  caseExportUrl,
  getCase,
  listActivity,
  listCases,
  postDecision,
  refreshAuthorEvidence,
  refreshAuthorSource,
} from "../../api/client";
import type {
  ActivityEvent,
  DecisionAction,
  RefreshSource,
  ValidationCase,
} from "../../api/types";
import { readCaseFilters } from "./filters";
import { orderCases, readQueueSort } from "./ordering";
import { useToast } from "../../components/Toast";
import { actionLabels } from "../../lib/decisions";
import { sourceLabel } from "../../lib/sources";
import CaseMeta from "./CaseMeta";
import DecisionBar from "./DecisionBar";
import Identity from "./Identity";
import Matrix from "./Matrix";
import styles from "./CasePage.module.css";

interface CaseData {
  reviewCase: ValidationCase;
  queue: ValidationCase[];
  notes: ActivityEvent[];
  queueSearch: string;
  relatedDataError: boolean;
}

type RefreshTarget = RefreshSource | "all";

async function loadCaseData(caseId: string, search: string): Promise<CaseData> {
  const reviewCase = await getCase(caseId);
  const queueParams = new URLSearchParams(search);
  if (!queueParams.has("scope") && !reviewCase.queue_eligible) {
    queueParams.set("scope", "archived");
  } else if (
    queueParams.get("scope") === "archived" &&
    reviewCase.queue_eligible
  ) {
    queueParams.delete("scope");
  }
  // Keep the case available when navigation or notes fail
  const [queueResult, activityResult] = await Promise.allSettled([
    listCases(readCaseFilters(queueParams)),
    listActivity(),
  ]);
  const { column, direction } = readQueueSort(queueParams);
  const queue = orderCases(
    queueResult.status === "fulfilled" ? queueResult.value : [reviewCase],
    column,
    direction,
  );
  const activity =
    activityResult.status === "fulfilled" ? activityResult.value : [];
  return {
    reviewCase,
    queue,
    notes: activity.filter(
      (event) => event.case_id === reviewCase.id && event.note,
    ),
    queueSearch: queueParams.toString(),
    relatedDataError:
      queueResult.status === "rejected" || activityResult.status === "rejected",
  };
}

export default function CasePage() {
  const { caseId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const showToast = useToast();
  const [data, setData] = useState<CaseData | null>(null);
  const [missing, setMissing] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [refreshing, setRefreshing] = useState<RefreshTarget | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const search = searchParams.toString();
  const requestVersion = useRef(0);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    const request = ++requestVersion.current;
    setData(null);
    setMissing(false);
    setLoadError(false);
    setRefreshing(null);
    setRefreshError(null);
    setDeciding(false);

    loadCaseData(caseId!, search)
      .then((loaded) => {
        if (request === requestVersion.current) setData(loaded);
      })
      .catch((error: unknown) => {
        if (request !== requestVersion.current) return;
        if (error instanceof ApiError && error.status === 404) {
          setMissing(true);
        } else {
          setLoadError(true);
        }
      });

    return () => {
      requestVersion.current += 1;
    };
  }, [caseId, search, loadAttempt]);

  if (missing) {
    return (
      <p className={styles.pageState} role="alert">
        Case not found: {caseId}
        {" · "}
        <Link to="/reviews" className={styles.stateLink}>
          back to queue
        </Link>
      </p>
    );
  }

  if (loadError) {
    return (
      <p className={styles.pageState} role="alert">
        Could not load the case{" "}
        <button
          type="button"
          onClick={() => setLoadAttempt((attempt) => attempt + 1)}
        >
          retry
        </button>
      </p>
    );
  }

  if (!data) return <p className={styles.pageState}>Loading case…</p>;

  const { reviewCase, queue, notes, queueSearch, relatedDataError } = data;

  const position = queue.findIndex((entry) => entry.id === reviewCase.id);
  const previous = position > 0 ? queue[position - 1] : null;
  const next =
    position >= 0 && position < queue.length - 1 ? queue[position + 1] : null;

  function decide(action: DecisionAction, note: string) {
    const request = requestVersion.current;
    setDeciding(true);

    return postDecision({
      case_id: reviewCase.id,
      action,
      note,
      expected_version: reviewCase.version,
    })
      .then((event) => {
        if (request !== requestVersion.current) return;
        showToast(`${actionLabels[event.action_type]}: ${event.target_name}`);
        navigate(
          next
            ? { pathname: `/reviews/${next.id}`, search: queueSearch }
            : { pathname: "/reviews", search: queueSearch },
        );
      })
      .catch((error: unknown) => {
        if (request === requestVersion.current)
          showToast(
            error instanceof ApiError && error.status === 409
              ? "Case changed. Reload and try again"
              : "Could not save the decision. Try again",
          );
        throw error;
      })
      .finally(() => {
        if (request === requestVersion.current) setDeciding(false);
      });
  }

  async function refreshEvidence(source?: RefreshSource) {
    if (refreshing || deciding) return;
    const request = requestVersion.current;
    let evidenceFetched = false;
    const target: RefreshTarget = source ?? "all";
    setRefreshing(target);
    setRefreshError(null);
    try {
      if (source) {
        await refreshAuthorSource(reviewCase.target.author_slug, source);
      } else {
        await refreshAuthorEvidence(reviewCase.target.author_slug);
      }
      evidenceFetched = true;
      if (request !== requestVersion.current) return;
      const loaded = await loadCaseData(reviewCase.id, search);
      if (request !== requestVersion.current) return;
      setData(loaded);
      showToast(
        source
          ? `${sourceLabel(source)} evidence fetched`
          : "All evidence fetched",
      );
    } catch {
      if (request !== requestVersion.current) return;
      setRefreshError(
        evidenceFetched
          ? "Evidence fetched. Could not reload the case"
          : source
            ? `Could not fetch ${sourceLabel(source)} evidence`
            : "Could not fetch evidence",
      );
    } finally {
      if (request === requestVersion.current) setRefreshing(null);
    }
  }

  return (
    <section className={styles.page}>
      <Link
        to={{ pathname: "/reviews", search: queueSearch }}
        className={styles.backLink}
      >
        ← back to queue
      </Link>

      {relatedDataError && (
        <p className={styles.relatedDataError} role="alert">
          Could not load queue navigation or notes{" "}
          <button
            type="button"
            disabled={deciding || refreshing !== null}
            onClick={() => setLoadAttempt((attempt) => attempt + 1)}
          >
            retry
          </button>
        </p>
      )}

      <div className={styles.header}>
        <div className={styles.identity}>
          <h1 className={styles.name}>{reviewCase.target.author_name}</h1>
          <CaseMeta reviewCase={reviewCase} />
        </div>

        <nav className={styles.queueNav} aria-label="Queue">
          <div className={styles.step}>
            <StepLink
              targetCase={previous}
              search={queueSearch}
              direction="previous"
              label="‹ prev"
            />
            {position >= 0 && (
              <span className={styles.position}>
                {position + 1} of {queue.length}
              </span>
            )}
            <StepLink
              targetCase={next}
              search={queueSearch}
              direction="next"
              label="next ›"
            />
          </div>
        </nav>
      </div>

      {refreshError && (
        <p className={styles.refreshError} role="alert">
          {refreshError}{" "}
          <button
            type="button"
            onClick={() => setLoadAttempt((attempt) => attempt + 1)}
          >
            reload case
          </button>
        </p>
      )}

      <DecisionBar
        status={reviewCase.status}
        notes={notes}
        busy={deciding || refreshing !== null}
        fetchingAll={refreshing === "all"}
        onDecide={decide}
        onFetchAll={() => void refreshEvidence()}
        exportUrl={caseExportUrl(reviewCase.id)}
      />

      <Matrix
        evidence={reviewCase.evidence}
        target={reviewCase.target}
        importedAt={reviewCase.dataset_imported_at}
        refreshing={refreshing}
        onRefreshSource={(source) => void refreshEvidence(source)}
        shares={Object.fromEntries(
          reviewCase.detail.candidate_ids.map((candidate) => [
            candidate.id,
            candidate.share,
          ]),
        )}
      />

      <Identity
        detail={reviewCase.detail}
        affectedCount={reviewCase.affected_count}
        caseId={reviewCase.id}
        search={queueSearch}
      />
    </section>
  );
}

function StepLink({
  targetCase,
  search,
  direction,
  label,
}: {
  targetCase: ValidationCase | null;
  search: string;
  direction: string;
  label: string;
}) {
  if (!targetCase) {
    return (
      <span
        className={`${styles.stepLink} ${styles.stepLinkOff}`}
        aria-hidden="true"
      >
        {label}
      </span>
    );
  }

  return (
    <Link
      to={{ pathname: `/reviews/${targetCase.id}`, search }}
      className={styles.stepLink}
      aria-label={`${direction} case, ${targetCase.target.author_name}`}
    >
      {label}
    </Link>
  );
}
