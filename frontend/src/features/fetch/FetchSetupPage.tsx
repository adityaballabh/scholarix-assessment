import styles from "./FetchPage.module.css";

export default function FetchSetupPage({
  busy,
  onRun,
}: {
  busy: boolean;
  onRun: () => void;
}) {
  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <p className={styles.wordmark}>Merge Review</p>
        <h1 className={styles.title}>Initial fetch pending</h1>
        <p className={styles.message}>
          Fetch external evidence to create the review queue
        </p>
        <div className={styles.actions}>
          <button type="button" disabled={busy} onClick={onRun}>
            fetch data
          </button>
        </div>
      </div>
    </main>
  );
}
