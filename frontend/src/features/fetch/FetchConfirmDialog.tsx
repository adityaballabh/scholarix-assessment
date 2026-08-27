import { useEffect, useRef } from "react";
import { formatRelativeTime } from "../../lib/datetime";
import styles from "./FetchConfirmDialog.module.css";

export default function FetchConfirmDialog({
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
  const initialFetch = lastCompletedAt === null;

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
          {initialFetch ? (
            <>
              Fetching data takes around 3 minutes. Are you sure you want to
              continue?
            </>
          ) : (
            <>
              Last fetched {formatRelativeTime(lastCompletedAt)}. Fetching data
              takes around 3 minutes.
            </>
          )}
        </p>
        {!initialFetch && (
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
