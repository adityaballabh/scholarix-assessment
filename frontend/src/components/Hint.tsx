import { useEffect, useLayoutEffect, useRef, useState } from "react";
import styles from "./Hint.module.css";

export default function Hint({
  text,
  align = "start",
}: {
  text: string;
  align?: "start" | "end";
}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const tooltipRef = useRef<HTMLSpanElement>(null);
  const open = (hovered || focused) && !dismissed;

  useEffect(() => {
    if (!hovered && !focused) setDismissed(false);
  }, [hovered, focused]);

  useEffect(() => {
    if (!open) return;
    function dismiss(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      setDismissed(true);
    }
    document.addEventListener("keydown", dismiss);
    return () => document.removeEventListener("keydown", dismiss);
  }, [open]);

  useLayoutEffect(() => {
    const tooltip = tooltipRef.current;
    if (!open || !tooltip) return;
    tooltip.style.transform = "";
    const { left, right } = tooltip.getBoundingClientRect();
    const shift =
      left < 8 ? 8 - left : Math.min(0, window.innerWidth - 8 - right);
    tooltip.style.transform = `translateX(${Math.round(shift)}px)`;
  }, [open, text, align]);

  return (
    <button
      type="button"
      className={styles.hint}
      aria-label={text}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
    >
      <span aria-hidden="true" className={styles.mark}>
        i
      </span>
      {open && (
        <span
          ref={tooltipRef}
          aria-hidden="true"
          className={`${styles.text} ${align === "end" ? styles.textEnd : ""}`}
        >
          {text}
        </span>
      )}
    </button>
  );
}
