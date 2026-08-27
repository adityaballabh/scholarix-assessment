import styles from "./FetchPage.module.css";

export default function UnreachablePage() {
  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <p className={styles.wordmark}>Merge Review</p>
        <h1 className={styles.title}>Cannot reach the server</h1>
        <p className={styles.message}>Retrying every few seconds</p>
      </div>
    </main>
  );
}
