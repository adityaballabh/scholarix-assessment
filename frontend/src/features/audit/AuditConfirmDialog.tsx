import { useEffect, useRef } from "react";
import styles from "./AuditConfirmDialog.module.css";

function relativeTime(value: string): string {
  const seconds = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 1000),
  );
  if (seconds < 3600) return "less than an hour ago";
  const hours = Math.floor(seconds / 3600);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} ${days === 1 ? "day" : "days"} ago`;
  const months = Math.floor(days / 30);
  if (months < 12) {
    return `${months} ${months === 1 ? "month" : "months"} ago`;
  }
  const years = Math.floor(months / 12);
  return `${years} ${years === 1 ? "year" : "years"} ago`;
}

export default function AuditConfirmDialog({
  open,
  busy,
  error,
  lastCompletedAt,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  busy: boolean;
  error: string | null;
  lastCompletedAt: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const initialAudit = lastCompletedAt === null;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      confirmRef.current?.focus();
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-label="Fetch data"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <div className={styles.body}>
        <p className={styles.message}>
          {initialAudit ? (
            <>
              Fetching data takes around 10 minutes. Are you sure you want to
              continue?
            </>
          ) : (
            <>
              Last fetched {relativeTime(lastCompletedAt)}. Fetching data takes
              around 10 minutes.
            </>
          )}
        </p>
        {!initialAudit && (
          <p className={styles.reviewLockout}>
            Review actions will be unavailable until the fetch is complete. Are
            you sure you want to continue?
          </p>
        )}
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.cancel}
            disabled={busy}
            onClick={onCancel}
          >
            cancel
          </button>
          <button
            type="button"
            ref={confirmRef}
            className={styles.primary}
            disabled={busy}
            onClick={onConfirm}
          >
            fetch data
          </button>
        </div>
      </div>
    </dialog>
  );
}
