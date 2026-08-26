import { useEffect, useRef, useState } from "react";

import type { User } from "../../api/types";
import styles from "./SessionMenu.module.css";

export function SessionMenu({
  user,
  onSignOut,
}: {
  user: User;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function dismissOutside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function dismissOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", dismissOutside);
    document.addEventListener("keydown", dismissOnEscape);
    return () => {
      document.removeEventListener("pointerdown", dismissOutside);
      document.removeEventListener("keydown", dismissOnEscape);
    };
  }, [open]);

  return (
    <div className={styles.root} ref={root}>
      <button
        type="button"
        className={styles.trigger}
        title={user.display_name}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((showing) => !showing)}
      >
        {user.display_name}
      </button>
      {open ? (
        <div className={styles.menu} role="menu">
          <p className={styles.name}>{user.display_name}</p>
          <button
            type="button"
            role="menuitem"
            className={styles.item}
            onClick={() => {
              setOpen(false);
              onSignOut();
            }}
          >
            sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
