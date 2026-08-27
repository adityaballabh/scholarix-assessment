import type { FetchRun } from "../../api/types";
import { FETCH_SOURCE_ORDER, sourceLabel } from "../../lib/sources";
import styles from "./FetchPage.module.css";

export default function FetchPage({
  fetchRun,
  busy,
  actionError,
  onRetry,
  onAbandon,
}: {
  fetchRun: FetchRun;
  busy: boolean;
  actionError: string | null;
  onRetry: () => void;
  onAbandon: () => void;
}) {
  const progress = Object.entries(fetchRun.source_progress).sort(
    ([left], [right]) =>
      FETCH_SOURCE_ORDER.indexOf(left) - FETCH_SOURCE_ORDER.indexOf(right),
  );
  const currentProgress = fetchRun.current_source
    ? fetchRun.source_progress[fetchRun.current_source]
    : undefined;
  const completed = currentProgress?.completed ?? 0;
  const total = currentProgress?.total ?? 0;

  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <p className={styles.wordmark}>Merge Review</p>
        <h1 className={styles.title}>
          {fetchRun.status === "failed" ? "Fetch failed" : "Fetch in progress"}
        </h1>
        {fetchRun.status === "failed" ? (
          <>
            <p className={styles.message} role="alert">
              Could not complete the fetch
            </p>
            <div className={styles.actions}>
              <button type="button" disabled={busy} onClick={onRetry}>
                retry fetch
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
              Fetching evidence for the full dataset. This usually takes around
              3 minutes. Review actions are paused
            </p>
            <div className={styles.overall}>
              <span>
                {fetchRun.current_source
                  ? sourceLabel(fetchRun.current_source)
                  : fetchRun.status}
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
                  <span>{sourceLabel(source)}</span>
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
