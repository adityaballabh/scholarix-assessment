import type {
  EvidenceRecord,
  EvidenceValueState,
  RefreshSource,
  ReviewTarget,
  SourceFetchStatus,
} from "../../api/types";
import Hint from "../../components/Hint";
import { formatFetchedAt } from "../../lib/datetime";
import { sourceLabel } from "../../lib/sources";
import { countedNoun } from "./labels";
import styles from "./Matrix.module.css";

const refreshableSources: RefreshSource[] = [
  "semantic_scholar",
  "openalex",
  "orcid",
];

function isRefreshSource(source: string): source is RefreshSource {
  return refreshableSources.includes(source as RefreshSource);
}

const fieldNames: Record<string, string> = {
  author_identity: "author identity",
  canonical_name: "canonical name",
  affiliation: "affiliation",
  profile_link: "profile link",
  orcid_id: "orcid",
  publications: "publications",
};

/**
 * The dataset's own values, by the evidence field they are checked against. This is the
 * baseline the sources are compared to rather than a source of its own, so it carries no
 * fetch state, no timestamp, and no supports/conflict styling.
 */
function datasetValues(target: ReviewTarget): Record<string, string | null> {
  return {
    canonical_name: target.author_name,
    affiliation: target.author_affiliation,
  };
}

const fetchNotes: Record<SourceFetchStatus, string> = {
  success: "200 ok",
  pending: "fetching",
  not_applicable: "no identifier available",
  empty: "empty response",
  not_found: "404 not found",
  rate_limited: "429 rate limited",
  timeout: "timed out",
  error: "request failed",
};

const emptyWords: Partial<Record<EvidenceValueState, string>> = {
  missing: "missing",
  unverifiable: "unverifiable",
};

const brokenFetches: SourceFetchStatus[] = [
  "rate_limited",
  "timeout",
  "error",
  "not_found",
];

function fieldName(field: string) {
  return fieldNames[field] ?? field.replace(/_/g, " ");
}

function fetchedLabel(iso: string | null) {
  return formatFetchedAt(iso) ?? "never attempted";
}

const TOP_SHARES = 3;

function recordLabel(record: EvidenceRecord, shares: Record<string, number>) {
  const refs = record.source_refs;
  if (refs.length === 0) return "—";
  if (refs.length === 1) return refs[0].id;

  const top = refs
    .map((ref) => shares[ref.id])
    .filter((share): share is number => share !== undefined)
    .sort((a, b) => b - a)
    .slice(0, TOP_SHARES);

  if (top.length === 0) return `${refs.length} ids`;

  const label = `top ${countedNoun(top.length, "ID", "IDs")}`;
  return `${label}: ${top.map((share) => `${Math.round(share)}%`).join(", ")}`;
}

export default function Matrix({
  evidence,
  shares = {},
  target,
  importedAt,
  refreshing,
  onRefreshSource,
}: {
  evidence: EvidenceRecord[];
  shares?: Record<string, number>;
  target: ReviewTarget;
  importedAt: string;
  refreshing: RefreshSource | "all" | null;
  onRefreshSource: (source: RefreshSource) => void;
}) {
  const provided = datasetValues(target);
  const sources = [...new Set(evidence.map((record) => record.source))];
  const fields = [...new Set(evidence.map((record) => record.field))];

  const at = (field: string, source: string) =>
    evidence.find(
      (record) => record.field === field && record.source === source,
    );

  const columnState = (source: string): SourceFetchStatus | null => {
    const cells = evidence.filter((record) => record.source === source);
    if (cells.length === 0) return null;

    const first = cells[0].fetch_status;
    const uniform = cells.every((record) => record.fetch_status === first);
    return uniform && first !== "success" ? first : null;
  };

  const deadColumns = new Map(
    sources.map((source) => [source, columnState(source)]),
  );

  const echoRows = new Map(
    sources.map((source) => [
      source,
      fields.find((field) => at(field, source) !== undefined),
    ]),
  );

  const conflicted = new Set(
    fields.filter((field) =>
      evidence.some(
        (record) => record.field === field && record.value_state === "conflict",
      ),
    ),
  );

  return (
    <div className={styles.scroll}>
      <div
        role="table"
        aria-label="Evidence by field and source"
        className={styles.matrix}
        style={
          {
            "--matrix-columns": `var(--matrix-rail, 36px) var(--matrix-field, 150px) repeat(${sources.length + 1}, minmax(0, 1fr))`,
            "--matrix-min-width": `calc(var(--matrix-rail, 36px) + var(--matrix-field, 150px) + ${(sources.length + 1) * 130}px)`,
          } as React.CSSProperties
        }
      >
        <div role="rowgroup" className={styles.head}>
          <div role="row" className={styles.row}>
            <div role="columnheader" className={styles.headCell}>
              <span className={styles.srOnly}>position</span>
            </div>
            <div role="columnheader" className={styles.headCell}>
              <span className={styles.srOnly}>field</span>
            </div>
            <div role="columnheader" className={styles.headCell}>
              <span className={styles.sourceTitle}>
                <span className={styles.sourceName}>Dataset</span>
              </span>
              {/* Two lines like the source columns: the label where they print an
                  identifier, the date where they print their fetch time. */}
              <span className={styles.provenance} title="">
                imported
              </span>
              <span className={styles.provenance} title="">
                {fetchedLabel(importedAt)}
              </span>
            </div>
            {sources.map((source) => {
              const state = deadColumns.get(source);
              const sample = evidence.find(
                (record) => record.source === source,
              );
              const refreshable = isRefreshSource(source);
              const applicable = sample?.fetch_status !== "not_applicable";

              return (
                <div
                  key={source}
                  role="columnheader"
                  className={`${styles.headCell} ${state ? styles.headCellDead : ""}`}
                >
                  <span className={styles.sourceTitle}>
                    <span className={styles.sourceName}>
                      {sourceLabel(source)}
                    </span>
                    {refreshable && (
                      <button
                        type="button"
                        className={styles.refreshSource}
                        disabled={refreshing !== null || !applicable}
                        aria-label={`fetch ${sourceLabel(source)} evidence`}
                        onClick={() => onRefreshSource(source)}
                      >
                        {refreshing === source ? "fetching" : "fetch"}
                      </button>
                    )}
                  </span>
                  <span className={styles.provenance} title="">
                    {sample ? recordLabel(sample, shares) : "—"}
                  </span>
                  {sample?.fetch_status !== "not_applicable" && (
                    <span className={styles.provenance} title="">
                      {fetchedLabel(sample?.fetched_at ?? null)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div role="rowgroup">
          {fields.map((field, index) => (
            <div role="row" className={styles.row} key={field}>
              <div role="cell" className={styles.position}>
                {index + 1}
              </div>
              <div role="rowheader" className={styles.fieldCell}>
                <span className={styles.fieldName}>{fieldName(field)}</span>
                {conflicted.has(field) && (
                  <span className={styles.conflictTag}>conflict</span>
                )}
              </div>
              <div role="cell" className={styles.cell}>
                {provided[field] && (
                  <span className={`${styles.cellLine} ${styles.value}`}>
                    {provided[field]}
                  </span>
                )}
              </div>
              {sources.map((source) => (
                <Cell
                  key={source}
                  record={at(field, source)}
                  source={source}
                  field={field}
                  columnState={deadColumns.get(source) ?? null}
                  echoes={echoRows.get(source) === field}
                  last={source === sources[sources.length - 1]}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Cell({
  record,
  source,
  field,
  columnState,
  echoes,
  last,
}: {
  record: EvidenceRecord | undefined;
  source: string;
  field: string;
  columnState: SourceFetchStatus | null;
  echoes: boolean;
  last: boolean;
}) {
  const hintAlign = last ? "end" : "start";
  if (columnState) {
    const broken = brokenFetches.includes(columnState);

    return (
      <div
        role="cell"
        className={`${styles.cell} ${broken ? styles.cellBroken : styles.cellNever}`}
      >
        {echoes ? (
          <>
            <span className={styles.absence}>{fetchNotes[columnState]}</span>
            {columnState !== "not_applicable" && (
              <span className={styles.reason}>no answer received</span>
            )}
          </>
        ) : (
          <span className={styles.srOnly}>
            {sourceLabel(source)} {fetchNotes[columnState]}, {fieldName(field)}{" "}
            unknown
          </span>
        )}
      </div>
    );
  }

  if (!record) {
    return (
      <div role="cell" className={styles.cell}>
        <span className={styles.srOnly}>
          {sourceLabel(source)} holds no {fieldName(field)} field
        </span>
      </div>
    );
  }

  const word =
    record.value_state === "missing" && field === "affiliation"
      ? "no affiliations found"
      : emptyWords[record.value_state];
  if (word || record.value === null) {
    return (
      <div role="cell" className={styles.cell}>
        <span className={styles.cellLine}>
          <span className={styles.absence}>{word ?? "absent"}</span>
          {record.interpretation && (
            <Hint text={record.interpretation} align={hintAlign} />
          )}
        </span>
      </div>
    );
  }

  const isConflict = record.value_state === "conflict";

  return (
    <div
      role="cell"
      className={`${styles.cell} ${isConflict ? styles.cellConflict : ""}`}
    >
      <span className={styles.cellLine}>
        <span className={styles.value}>{record.value}</span>
        {isConflict && record.interpretation && (
          <Hint text={record.interpretation} align={hintAlign} />
        )}
      </span>
    </div>
  );
}
