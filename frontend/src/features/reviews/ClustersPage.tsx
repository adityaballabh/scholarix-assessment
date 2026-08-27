import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError, getCase } from "../../api/client";
import type { ValidationCase } from "../../api/types";
import CaseMeta from "./CaseMeta";
import { pluralNoun } from "./labels";
import { leadTitle, yearSpan } from "./years";
import styles from "./ClustersPage.module.css";

export default function ClustersPage() {
  const { caseId } = useParams();
  const [searchParams] = useSearchParams();
  const [reviewCase, setReviewCase] = useState<ValidationCase | null>(null);
  const [missing, setMissing] = useState(false);
  const [openCandidateIds, setOpenCandidateIds] = useState<string[]>([]);
  const search = searchParams.toString();
  const [loadError, setLoadError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setReviewCase(null);
    setMissing(false);
    setLoadError(false);
    setOpenCandidateIds([]);

    getCase(caseId!)
      .then((found) => {
        if (active) setReviewCase(found);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 404) setMissing(true);
        else setLoadError(true);
      });

    return () => {
      active = false;
    };
  }, [caseId, loadAttempt]);

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

  if (loadError)
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

  if (!reviewCase) return <p className={styles.pageState}>Loading case…</p>;

  const candidates = reviewCase.detail.candidate_ids;
  function toggleCandidate(id: string) {
    setOpenCandidateIds((current) =>
      current.includes(id)
        ? current.filter((openId) => openId !== id)
        : [...current, id],
    );
  }

  return (
    <section className={styles.page}>
      <Link
        to={{ pathname: `/reviews/${reviewCase.id}`, search }}
        className={styles.backLink}
      >
        ← back to case
      </Link>

      <div className={styles.header}>
        <h1 className={styles.name}>{reviewCase.target.author_name}</h1>
        <CaseMeta reviewCase={reviewCase} />
      </div>

      <ol className={styles.clusters}>
        {candidates.map((candidate, index) => {
          const expanded = openCandidateIds.includes(candidate.id);
          const panelId = `cluster-${candidate.id}`;
          const candidateYears = yearSpan(candidate);

          return (
            <li className={styles.cluster} key={candidate.id}>
              <button
                type="button"
                className={styles.clusterRow}
                aria-expanded={expanded}
                aria-controls={panelId}
                onClick={() => toggleCandidate(candidate.id)}
              >
                <span className={styles.rail}>
                  <span className={styles.caret} aria-hidden="true">
                    {expanded ? "⌄" : "›"}
                  </span>
                  <span className={styles.position}>{index + 1}</span>
                </span>
                <span className={styles.identifier}>{candidate.id}</span>
                <span className={styles.share}>
                  {candidate.share.toFixed(1)}%
                </span>
                <span className={styles.span}>{candidateYears ?? "—"}</span>
                <span className={styles.title} title="">
                  {leadTitle(candidate)}
                </span>
              </button>

              {expanded && (
                <div id={panelId} className={styles.panel}>
                  <p className={styles.panelCount}>
                    {pluralNoun(
                      candidate.publications.length,
                      "publication",
                      "publications",
                    )}
                  </p>
                  <ol className={styles.publications}>
                    {candidate.publications.map((publication, position) => (
                      <li
                        className={styles.publication}
                        key={`${position}-${publication.title}`}
                      >
                        <span className={styles.position}>{position + 1}</span>
                        <span className={styles.publicationYear}>
                          {publication.year ?? "—"}
                        </span>
                        <span className={styles.publicationTitle}>
                          {publication.title}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
