import type { FetchRun } from "../../api/types";
import { FETCH_SOURCE_ORDER, sourceLabel } from "../../lib/sources";
import styles from "./FetchPage.module.css";

export default function FetchPage({
  fetch,
  busy,
  actionError,
  onRetry,
  onAbandon,
}: {
  fetch: FetchRun;
  busy: boolean;
  actionError: string | null;
  onRetry: () => void;
  onAbandon: () => void;
}) {
  const progress = Object.entries(fetch.source_progress).sort(
    ([left], [right]) =>
      FETCH_SOURCE_ORDER.indexOf(left) - FETCH_SOURCE_ORDER.indexOf(right),
  );
  const currentProgress = fetch.current_source
    ? fetch.source_progress[fetch.current_source]
    : undefined;
  const completed = currentProgress?.completed ?? 0;
  const total = currentProgress?.total ?? 0;

  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <p className={styles.wordmark}>Merge Review</p>
        <h1 className={styles.title}>
          {fetch.status === "failed" ? "Fetch failed" : "Fetch in progress"}
        </h1>
        {fetch.status === "failed" ? (
          <>
            <p className={styles.message} role="alert">
              The fetch could not be completed.
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
              External evidence is being fetched for the entire dataset. This
              usually takes around 5 minutes. Review actions are paused.
            </p>
            <div className={styles.overall}>
              <span>
                {fetch.current_source
                  ? sourceLabel(fetch.current_source)
                  : fetch.status}
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
