import { useEffect, useRef, useState } from "react";
import type {
  ActivityEvent,
  DecisionAction,
  ReviewStatus,
} from "../../api/types";
import { ApiError } from "../../api/client";
import { formatFetchedAt } from "../../lib/datetime";
import { statusText } from "../../lib/decisions";
import styles from "./DecisionBar.module.css";

interface DecisionOption {
  action: DecisionAction;
  label: string;
  resultingStatus?: ReviewStatus;
  noteRequired?: boolean;
}

const decisionOptions: DecisionOption[] = [
  {
    action: "reopen",
    label: "pending",
    resultingStatus: "pending",
  },
  {
    action: "confirm_one_author",
    label: "one author",
    resultingStatus: "one_author",
  },
  {
    action: "flag_for_split",
    label: "needs split",
    resultingStatus: "needs_split",
  },
  {
    action: "mark_uncertain",
    label: "uncertain",
    resultingStatus: "uncertain",
  },
  {
    action: "defer",
    label: "defer",
    resultingStatus: "deferred",
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
  const [selectedDecision, setSelectedDecision] =
    useState<DecisionOption | null>(null);
  const [viewingNotes, setViewingNotes] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const available = decisionOptions.filter(
    (decision) => decision.resultingStatus !== status,
  );
  const [note, setNote] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const open = selectedDecision !== null || viewingNotes;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [selectedDecision, viewingNotes]);

  function open(decision: DecisionOption, trigger: HTMLButtonElement) {
    triggerRef.current = trigger;
    setNote("");
    setSelectedDecision(decision);
  }

  const noteRequiredAndEmpty =
    selectedDecision?.noteRequired === true && note.trim() === "";

  function close() {
    if (busy) return;
    setSelectedDecision(null);
    setViewingNotes(false);
    setSubmitError(null);
    triggerRef.current?.focus();
  }

  function confirm() {
    if (!selectedDecision || busy || noteRequiredAndEmpty) return;
    setSubmitError(null);
    void onDecide(selectedDecision.action, note)
      .then(close)
      .catch((cause) => {
        setSubmitError(
          cause instanceof ApiError && cause.status === 401
            ? "Sign in to record this decision"
            : "Could not record the decision. Reload the case and try again",
        );
      });
  }

  return (
    <div className={styles.bar}>
      <div className={styles.actions}>
        {available.map((decision) => (
          <button
            key={decision.action}
            type="button"
            className={styles.action}
            disabled={busy}
            onClick={(event) => open(decision, event.currentTarget)}
          >
            {decision.label}
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
        aria-label={
          selectedDecision?.label ?? (viewingNotes ? "notes" : undefined)
        }
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
                        {statusText(event.before)} → {statusText(event.after)}
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

        {selectedDecision && (
          <div className={styles.dialogBody}>
            <p className={styles.dialogTitle}>{selectedDecision.label}</p>
            <textarea
              autoFocus
              aria-label={
                selectedDecision.noteRequired ? "note" : "optional note"
              }
              className={styles.noteField}
              value={note}
              rows={4}
              placeholder={
                selectedDecision.noteRequired ? "note" : "optional note"
              }
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== "Enter" || event.shiftKey) return;
                event.preventDefault();
                if (!noteRequiredAndEmpty) confirm();
              }}
            />
            <div className={styles.dialogActions}>
              <span
                className={submitError ? styles.submitError : styles.submitHint}
              >
                {submitError ?? (noteRequiredAndEmpty ? "" : "enter to submit")}
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
                data-hint={
                  noteRequiredAndEmpty ? "A note is required" : undefined
                }
              >
                <button
                  type="button"
                  className={`${styles.action} ${styles.primary}`}
                  disabled={noteRequiredAndEmpty || busy}
                  onClick={confirm}
                >
                  {selectedDecision.label}
                </button>
              </span>
            </div>
          </div>
        )}
      </dialog>

      <span aria-live="polite" className={styles.srOnly}>
        Case is {statusText(status)}
      </span>
    </div>
  );
}
