import styles from "./Hint.module.css";

export default function Hint({
  text,
  align = "start",
}: {
  text: string;
  align?: "start" | "end";
}) {
  return (
    <button type="button" className={styles.hint} aria-label={text}>
      <span aria-hidden="true" className={styles.mark}>
        i
      </span>
      <span
        aria-hidden="true"
        className={`${styles.text} ${align === "end" ? styles.textEnd : ""}`}
      >
        {text}
      </span>
    </button>
  );
}
