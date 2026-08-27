import { useEffect, useRef } from "react";

import type { User } from "../../api/types";
import { SignInForm } from "./SignInForm";
import styles from "./SignInDialog.module.css";

export function SignInDialog({
  open,
  onDismiss,
  onSignedIn,
}: {
  open: boolean;
  onDismiss: () => void;
  onSignedIn: (user: User) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-label="Sign in"
      onCancel={(event) => {
        event.preventDefault();
        onDismiss();
      }}
    >
      <div className={styles.body}>
        <p className={styles.message}>Sign in to make changes</p>
        {open ? (
          <SignInForm
            autoFocus
            initialMode="register"
            onSignedIn={onSignedIn}
          />
        ) : null}
        <button
          type="button"
          className={styles.close}
          aria-label="Close"
          onClick={onDismiss}
        >
          &times;
        </button>
      </div>
    </dialog>
  );
}
