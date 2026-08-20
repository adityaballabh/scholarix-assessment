import type { ReactNode } from "react";
import styles from "./SortHeader.module.css";

export type SortDirection = "asc" | "desc";

export default function SortHeader({
  label,
  active,
  direction,
  clearable,
  onSort,
  children,
}: {
  label: string;
  active: boolean;
  direction: SortDirection;
  clearable?: boolean;
  onSort: (direction: SortDirection | null) => void;
  children?: ReactNode;
}) {
  const next: SortDirection | null = !active
    ? "desc"
    : direction === "desc"
      ? "asc"
      : clearable
        ? null
        : "desc";
  const up = active && direction === "asc";
  const down = active && direction === "desc";

  return (
    <button
      type="button"
      className={`${styles.header} ${active ? styles.active : ""}`}
      aria-label={
        next === null
          ? `Clear sorting by ${label}`
          : `Sort by ${label}, ${next}ending`
      }
      onClick={() => onSort(next)}
    >
      {children ?? label}
      <svg
        aria-hidden="true"
        viewBox="0 0 9 12"
        className={styles.arrows}
        fill="none"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path
          d="M1 4.6 4.5 1.2 8 4.6"
          className={up ? styles.on : styles.off}
        />
        <path
          d="M1 7.4 4.5 10.8 8 7.4"
          className={down ? styles.on : styles.off}
        />
      </svg>
    </button>
  );
}
