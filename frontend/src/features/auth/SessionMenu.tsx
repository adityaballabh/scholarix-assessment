import { useEffect, useId, useRef, useState } from "react";
import type { User } from "../../api/types";
import styles from "./SessionMenu.module.css";

export function SessionMenu({
  user,
  onSignOut,
}: {
  user: User;
  onSignOut: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    function dismissOutside(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", dismissOutside);
    return () => document.removeEventListener("pointerdown", dismissOutside);
  }, [open]);

  async function handleSignOut() {
    if (signingOut) return;
    setSigningOut(true);
    setError(null);
    try {
      await onSignOut();
      setOpen(false);
    } catch {
      setError("Could not sign out. Try again");
      triggerRef.current?.focus();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div
      className={styles.root}
      ref={rootRef}
      onBlur={(event) => {
        if (!signingOut && !event.currentTarget.contains(event.relatedTarget))
          setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          event.stopPropagation();
          setOpen(false);
          triggerRef.current?.focus();
        }
      }}
    >
      <button
        type="button"
        ref={triggerRef}
        className={styles.trigger}
        title={user.display_name}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((showing) => !showing)}
      >
        {user.display_name}
      </button>
      {open && (
        <div className={styles.menu} id={panelId}>
          <p className={styles.name}>{user.display_name}</p>
          <button
            type="button"
            className={styles.item}
            disabled={signingOut}
            onClick={() => void handleSignOut()}
          >
            {signingOut ? "signing out…" : "sign out"}
          </button>
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
