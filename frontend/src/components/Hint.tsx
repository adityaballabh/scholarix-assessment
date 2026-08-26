import { useLayoutEffect, useRef, useState } from "react";

import styles from "./Hint.module.css";

export default function Hint({
  text,
  align = "start",
}: {
  text: string;
  align?: "start" | "end";
}) {
  const [open, setOpen] = useState(false);
  const textRef = useRef<HTMLSpanElement>(null);

  // Keep the tooltip on screen: nudge it back inside the viewport when it
  // would overflow an edge (routine on a narrow phone).
  useLayoutEffect(() => {
    const el = textRef.current;
    if (!open || !el) return;
    el.style.transform = "";
    const margin = 8;
    const { left, right } = el.getBoundingClientRect();
    let shift = 0;
    if (left < margin) shift = margin - left;
    else if (right > window.innerWidth - margin)
      shift = window.innerWidth - margin - right;
    if (shift) el.style.transform = `translateX(${Math.round(shift)}px)`;
  }, [open, text]);

  return (
    <button
      type="button"
      className={styles.hint}
      aria-label={text}
      onPointerEnter={() => setOpen(true)}
      onPointerLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span aria-hidden="true" className={styles.mark}>
        i
      </span>
      {open && (
        <span
          ref={textRef}
          aria-hidden="true"
          className={`${styles.text} ${align === "end" ? styles.textEnd : ""}`}
        >
          {text}
        </span>
      )}
    </button>
  );
}
