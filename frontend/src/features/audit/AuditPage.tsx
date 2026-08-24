import type { AuditRun } from "../../api/types";
import styles from "./AuditPage.module.css";

const sourceLabels: Record<string, string> = {
  openalex_authors: "OpenAlex authors",
  openalex_author_publications: "OpenAlex author publications",
  openalex_publications: "OpenAlex publications",
  orcid: "ORCID",
  semantic_scholar: "Semantic Scholar",
  case_generation: "Case generation",
};
const sourceOrder = Object.keys(sourceLabels);

export default function AuditPage({
  audit,
  busy,
  actionError,
  onRetry,
  onAbandon,
}: {
  audit: AuditRun;
  busy: boolean;
  actionError: string | null;
  onRetry: () => void;
  onAbandon: () => void;
}) {
  const progress = Object.entries(audit.source_progress).sort(
    ([left], [right]) => sourceOrder.indexOf(left) - sourceOrder.indexOf(right),
  );
  const currentProgress = audit.current_source
    ? audit.source_progress[audit.current_source]
    : undefined;
  const completed = currentProgress?.completed ?? 0;
  const total = currentProgress?.total ?? 0;

  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <p className={styles.wordmark}>Merge Review</p>
        <h1 className={styles.title}>
          {audit.status === "failed" ? "Audit failed" : "Fetch in progress"}
        </h1>
        {audit.status === "failed" ? (
          <>
            <p className={styles.message} role="alert">
              {audit.error || "The audit could not be completed."}
            </p>
            <div className={styles.actions}>
              <button type="button" disabled={busy} onClick={onRetry}>
                retry audit
              </button>
              <button type="button" disabled={busy} onClick={onAbandon}>
                return to app
              </button>
            </div>
            {actionError && (
              <p className={styles.actionError} role="alert">
                {actionError}
              </p>
            )}
          </>
        ) : (
          <>
            <p className={styles.message}>
              External evidence is being fetched for the entire dataset. This
              usually takes around 10 minutes. Review actions are paused.
            </p>
            <div className={styles.overall}>
              <span>
                {audit.current_source
                  ? (sourceLabels[audit.current_source] ?? audit.current_source)
                  : audit.status}
              </span>
              <span>
                {completed.toLocaleString()} / {total.toLocaleString()}
              </span>
            </div>
            <progress
              className={styles.progress}
              max={Math.max(total, 1)}
              value={completed}
            />
            <ol className={styles.sources}>
              {progress.map(([source, state]) => (
                <li className={styles.source} key={source}>
                  <span>{sourceLabels[source] ?? source}</span>
                  <span>
                    {state.completed.toLocaleString()} /{" "}
                    {state.total.toLocaleString()}
                  </span>
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </main>
  );
}
