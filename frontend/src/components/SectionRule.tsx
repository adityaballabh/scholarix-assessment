import type { ReactNode } from "react";

export default function SectionRule({
  label,
  hint,
}: {
  label: string;
  hint?: ReactNode;
}) {
  return (
    <div className="sectionRule">
      <span className="sectionLabel">{label}</span>
      {hint && <span className="sectionHint">{hint}</span>}
    </div>
  );
}
