import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import styles from "./Select.module.css";

export interface SelectOption<T extends string> {
  value: T;
  label: string;
}

interface SelectProps<T extends string> {
  label: string;
  prefix?: string;
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
}

const TYPEAHEAD_RESET_MS = 600;

export default function Select<T extends string>({
  label,
  prefix,
  value,
  options,
  onChange,
}: SelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const typeahead = useRef({ buffer: "", timer: 0 });
  const listId = useId();

  const selectedIndex = Math.max(
    options.findIndex((option) => option.value === value),
    0,
  );
  const selected = options[selectedIndex];

  useEffect(() => {
    if (!open) return;

    setActiveIndex(selectedIndex);
    typeahead.current.buffer = "";
    listRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function closeOnOutside(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }

    document.addEventListener("pointerdown", closeOnOutside);
    return () => document.removeEventListener("pointerdown", closeOnOutside);
  }, [open]);

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  function commit(index: number) {
    onChange(options[index].value);
    close();
  }

  function jumpToTyped(character: string) {
    window.clearTimeout(typeahead.current.timer);
    typeahead.current.buffer += character.toLowerCase();
    typeahead.current.timer = window.setTimeout(() => {
      typeahead.current.buffer = "";
    }, TYPEAHEAD_RESET_MS);

    const match = options.findIndex((option) =>
      option.label.toLowerCase().startsWith(typeahead.current.buffer),
    );
    if (match >= 0) setActiveIndex(match);
  }

  function onKeyDown(event: KeyboardEvent<HTMLUListElement>) {
    const lastIndex = options.length - 1;

    if (
      event.key.length === 1 &&
      !event.metaKey &&
      !event.ctrlKey &&
      !(event.key === " " && typeahead.current.buffer === "")
    ) {
      event.preventDefault();
      jumpToTyped(event.key);
      return;
    }

    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActiveIndex((index) => Math.min(index + 1, lastIndex));
        break;
      case "ArrowUp":
        event.preventDefault();
        setActiveIndex((index) => Math.max(index - 1, 0));
        break;
      case "Home":
        event.preventDefault();
        setActiveIndex(0);
        break;
      case "End":
        event.preventDefault();
        setActiveIndex(lastIndex);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        commit(activeIndex);
        break;
      case "Escape":
        event.preventDefault();
        close();
        break;
      case "Tab":
        setOpen(false);
        break;
    }
  }

  return (
    <div className={styles.select} ref={rootRef}>
      <button
        type="button"
        ref={triggerRef}
        className={styles.trigger}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label}: ${selected.label}`}
        onClick={() => setOpen((isOpen) => !isOpen)}
      >
        <span className={styles.triggerLabel} title={selected.label}>
          {prefix ? `${prefix} ${selected.label}` : selected.label}
        </span>
        <span className={styles.caret} aria-hidden="true" />
      </button>

      {open && (
        <ul
          ref={listRef}
          role="listbox"
          tabIndex={-1}
          aria-label={label}
          aria-activedescendant={`${listId}-${activeIndex}`}
          className={styles.list}
          onKeyDown={onKeyDown}
        >
          {options.map((option, index) => (
            <li
              key={option.value}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={option.value === value}
              className={`${styles.option} ${index === activeIndex ? styles.activeOption : ""}`}
              onPointerMove={() => setActiveIndex(index)}
              onClick={() => commit(index)}
            >
              {option.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
