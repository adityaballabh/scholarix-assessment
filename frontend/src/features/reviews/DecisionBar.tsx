import { useEffect, useRef, useState } from "react";
import type {
  ActivityEvent,
  DecisionAction,
  ReviewStatus,
} from "../../api/types";
import { ApiError } from "../../api/client";
import { formatFetchedAt } from "../../lib/datetime";
import styles from "./DecisionBar.module.css";

interface Judgement {
  action: DecisionAction;
  label: string;
  /** The status this lands on, hidden when the case is already there */
  status?: ReviewStatus;
  noteRequired?: boolean;
}

const judgements: Judgement[] = [
  {
    action: "reopen",
    label: "pending",
    status: "pending",
  },
  {
    action: "confirm_one_author",
    label: "one author",
    status: "one_author",
  },
  {
    action: "flag_for_split",
    label: "needs split",
    status: "needs_split",
  },
  {
    action: "mark_uncertain",
    label: "uncertain",
    status: "uncertain",
  },
  {
    action: "defer",
    label: "defer",
    status: "deferred",
  },
  {
    action: "note",
    label: "note only",
    noteRequired: true,
  },
];

export default function DecisionBar({
  status,
  notes,
  busy,
  fetchingAll,
  exportUrl,
  onDecide,
  onFetchAll,
}: {
  status: ReviewStatus;
  notes: ActivityEvent[];
  busy: boolean;
  fetchingAll: boolean;
  exportUrl: string;
  onDecide: (action: DecisionAction, note: string) => Promise<void>;
  onFetchAll: () => void;
}) {
  const [pending, setPending] = useState<Judgement | null>(null);
  const [viewingNotes, setViewingNotes] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const available = judgements.filter(
    (judgement) => judgement.status !== status,
  );
  const [note, setNote] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const open = pending !== null || viewingNotes;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [pending, viewingNotes]);

  function open(judgement: Judgement, trigger: HTMLButtonElement) {
    triggerRef.current = trigger;
    setNote("");
    setPending(judgement);
  }

  const blocked = pending?.noteRequired === true && note.trim() === "";

  function close() {
    if (busy) return;
    setPending(null);
    setViewingNotes(false);
    setFailure(null);
    triggerRef.current?.focus();
  }

  function confirm() {
    if (!pending || busy) return;
    setFailure(null);
    void onDecide(pending.action, note)
      .then(close)
      .catch((cause) => {
        setFailure(
          cause instanceof ApiError && cause.status === 401
            ? "Sign in to record this decision."
            : "The decision was not recorded. Reload the case and try again.",
        );
      });
  }

  return (
    <div className={styles.bar}>
      <div className={styles.actions}>
        {available.map((judgement) => (
          <button
            key={judgement.action}
            type="button"
            className={styles.action}
            disabled={busy}
            onClick={(event) => open(judgement, event.currentTarget)}
          >
            {judgement.label}
          </button>
        ))}
        {notes.length > 0 && (
          <button
            type="button"
            className={styles.action}
            onClick={(event) => {
              triggerRef.current = event.currentTarget;
              setViewingNotes(true);
            }}
          >
            view notes ({notes.length})
          </button>
        )}
        <button
          type="button"
          className={`${styles.action} ${styles.fetchAll}`}
          disabled={busy}
          onClick={onFetchAll}
        >
          {fetchingAll ? "fetching" : "fetch all evidence"}
        </button>
        <a
          className={`${styles.action} ${styles.actionLink}`}
          href={exportUrl}
          download
        >
          export evidence
        </a>
      </div>

      <dialog
        ref={dialogRef}
        className={styles.dialog}
        aria-label={pending?.label ?? (viewingNotes ? "notes" : undefined)}
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
      >
        {viewingNotes && (
          <div className={styles.dialogBody}>
            <p className={styles.dialogTitle}>notes</p>
            <ol className={styles.notes}>
              {notes.map((event) => (
                <li className={styles.note} key={event.id}>
                  <p className={styles.noteMeta}>
                    <span>{event.actor}</span>
                    {event.before !== event.after && (
                      <span>
                        {event.before?.replace(/_/g, " ")} →{" "}
                        {event.after?.replace(/_/g, " ")}
                      </span>
                    )}
                    <span>{formatFetchedAt(event.created_at)}</span>
                  </p>
                  <p className={styles.noteBody}>{event.note}</p>
                </li>
              ))}
            </ol>
            <div className={styles.dialogActions}>
              <button type="button" className={styles.action} onClick={close}>
                close
              </button>
            </div>
          </div>
        )}

        {pending && (
          <div className={styles.dialogBody}>
            <p className={styles.dialogTitle}>{pending.label}</p>
            <textarea
              autoFocus
              className={styles.noteField}
              value={note}
              rows={4}
              placeholder={pending.noteRequired ? "note" : "optional note"}
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== "Enter" || event.shiftKey) return;
                event.preventDefault();
                if (!blocked) confirm();
              }}
            />
            <div className={styles.dialogActions}>
              <span
                className={failure ? styles.submitError : styles.submitHint}
              >
                {failure ?? (blocked ? "" : "enter to submit")}
              </span>
              <button
                type="button"
                className={styles.action}
                disabled={busy}
                onClick={close}
              >
                cancel
              </button>
              <span
                className={styles.guard}
                data-hint={blocked ? "A note is required" : undefined}
              >
                <button
                  type="button"
                  className={`${styles.action} ${styles.primary}`}
                  disabled={blocked || busy}
                  onClick={confirm}
                >
                  {pending.label}
                </button>
              </span>
            </div>
          </div>
        )}
      </dialog>

      <span aria-live="polite" className={styles.srOnly}>
        Case is {status.replace(/_/g, " ")}
      </span>
    </div>
  );
}
