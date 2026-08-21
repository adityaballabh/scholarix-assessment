import { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  getCase,
  listActivity,
  listCases,
  postDecision,
} from "../../api/client";
import type {
  ActivityEvent,
  DecisionAction,
  ValidationCase,
} from "../../api/types";
import { readCaseFilters } from "./filters";
import { useToast } from "../../components/Toast";
import { actionLabels } from "../../lib/decisions";
import CaseMeta from "./CaseMeta";
import DecisionBar from "./DecisionBar";
import Identity from "./Identity";
import Matrix from "./Matrix";
import styles from "./CasePage.module.css";

interface CaseData {
  reviewCase: ValidationCase;
  queue: ValidationCase[];
  notes: ActivityEvent[];
}

export default function CasePage() {
  const { caseId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const showToast = useToast();
  const [data, setData] = useState<CaseData | null>(null);
  const [missing, setMissing] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const search = searchParams.toString();

  useEffect(() => {
    let active = true;
    setData(null);
    setMissing(false);

    Promise.all([
      getCase(caseId!),
      listCases(readCaseFilters(new URLSearchParams(search))),
      listActivity(),
    ])
      .then(([reviewCase, queue, activity]) => {
        if (!active) return;
        const notes = activity.filter(
          (event) => event.case_id === reviewCase.id && event.note,
        );
        setData({ reviewCase, queue, notes });
      })
      .catch(() => {
        if (active) setMissing(true);
      });

    return () => {
      active = false;
    };
  }, [caseId, search]);

  if (missing) {
    return (
      <p className={styles.pageState} role="alert">
        No case with id {caseId}
        {" · "}
        <Link to="/reviews" className={styles.stateLink}>
          back to the queue
        </Link>
      </p>
    );
  }

  if (!data) return <p className={styles.pageState}>Loading case…</p>;

  const { reviewCase, queue, notes } = data;

  const position = queue.findIndex((entry) => entry.id === reviewCase.id);
  const previous = position > 0 ? queue[position - 1] : null;
  const next =
    position >= 0 && position < queue.length - 1 ? queue[position + 1] : null;

  function decide(action: DecisionAction, note: string) {
    setDeciding(true);

    postDecision({ case_id: reviewCase.id, action, note })
      .then((event) => {
        showToast(`${actionLabels[event.action_type]} · ${event.target_name}`);
        navigate(
          next
            ? { pathname: `/reviews/${next.id}`, search }
            : { pathname: "/reviews", search },
        );
      })
      .finally(() => setDeciding(false));
  }

  return (
    <section className={styles.page}>
      <Link to={{ pathname: "/reviews", search }} className={styles.backLink}>
        ← back to queue
      </Link>

      <div className={styles.header}>
        <div className={styles.identity}>
          <h1 className={styles.name}>{reviewCase.target.author_name}</h1>
          <CaseMeta reviewCase={reviewCase} />
        </div>

        <nav className={styles.queueNav} aria-label="Queue">
          <div className={styles.step}>
            <StepLink
              to={previous}
              search={search}
              direction="previous"
              label="‹ prev"
            />
            {position >= 0 && (
              <span className={styles.position}>
                {position + 1} of {queue.length}
              </span>
            )}
            <StepLink
              to={next}
              search={search}
              direction="next"
              label="next ›"
            />
          </div>
        </nav>
      </div>

      <DecisionBar
        status={reviewCase.status}
        notes={notes}
        busy={deciding}
        onDecide={decide}
      />

      <Matrix
        evidence={reviewCase.evidence}
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
        search={search}
      />
    </section>
  );
}

function StepLink({
  to,
  search,
  direction,
  label,
}: {
  to: ValidationCase | null;
  search: string;
  direction: string;
  label: string;
}) {
  if (!to) {
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
      to={{ pathname: `/reviews/${to.id}`, search }}
      className={styles.stepLink}
      aria-label={`${direction} case, ${to.target.author_name}`}
    >
      {label}
    </Link>
  );
}
