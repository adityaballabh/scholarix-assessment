import { useEffect, useRef, useState } from "react";
import type { DecisionAction, ReviewStatus } from "../../api/types";
import styles from "./DecisionBar.module.css";

interface Judgement {
  action: DecisionAction;
  label: string;
  noteRequired?: boolean;
}

// No per-cluster resolution: S2 clusters are another system's inference and
// carry no key into OpenAlex, so the decision is a judgement, not a split.
const judgements: Judgement[] = [
  {
    action: "confirm_one_author",
    label: "one author",
  },
  {
    action: "flag_for_split",
    label: "needs split",
  },
  {
    action: "mark_uncertain",
    label: "uncertain",
  },
  {
    action: "defer",
    label: "defer",
  },
  {
    action: "note",
    label: "note only",
    noteRequired: true,
  },
];

export default function DecisionBar({
  status,
  busy,
  onDecide,
}: {
  status: ReviewStatus;
  busy: boolean;
  onDecide: (action: DecisionAction, note: string) => void;
}) {
  const [pending, setPending] = useState<Judgement | null>(null);
  const [note, setNote] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (pending && !dialog.open) dialog.showModal();
    if (!pending && dialog.open) dialog.close();
  }, [pending]);

  function open(judgement: Judgement, trigger: HTMLButtonElement) {
    triggerRef.current = trigger;
    setNote("");
    setPending(judgement);
  }

  function close() {
    setPending(null);
    // No-op while a decision is in flight, since the trigger is disabled then;
    // the effect below finishes the job.
    triggerRef.current?.focus();
  }

  const wasBusy = useRef(busy);
  useEffect(() => {
    if (wasBusy.current && !busy) triggerRef.current?.focus();
    wasBusy.current = busy;
  }, [busy]);

  function confirm() {
    if (!pending) return;
    onDecide(pending.action, note);
    close();
  }

  const blocked = pending?.noteRequired === true && note.trim() === "";

  return (
    <div className={styles.bar}>
      <div className={styles.actions}>
        {judgements.map((judgement) => (
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
      </div>

      <dialog
        ref={dialogRef}
        className={styles.dialog}
        aria-label={pending?.label}
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
      >
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
            />
            <div className={styles.dialogActions}>
              <button type="button" className={styles.action} onClick={close}>
                cancel
              </button>
              <button
                type="button"
                className={`${styles.action} ${styles.primary}`}
                disabled={blocked}
                onClick={confirm}
              >
                {pending.label}
              </button>
            </div>
          </div>
        )}
      </dialog>

      <span aria-live="polite" className={styles.srOnly}>
        Case is {status.replace(/_/g, " ")}.
      </span>
    </div>
  );
}
