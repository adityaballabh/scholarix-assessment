import type {
  EvidenceRecord,
  EvidenceValueState,
  RefreshSource,
  ReviewTarget,
  SourceFetchStatus,
} from "../../api/types";
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
  const datasetByField = datasetValues(target);
  const sources = [...new Set(evidence.map((record) => record.source))];
  const fields = [...new Set(evidence.map((record) => record.field))];

  const recordFor = (field: string, source: string) =>
    evidence.find(
      (record) => record.field === field && record.source === source,
    );

  const columnFetchState = (source: string): SourceFetchStatus | null => {
    const cells = evidence.filter((record) => record.source === source);
    if (cells.length === 0) return null;

    const first = cells[0].fetch_status;
    const uniform = cells.every((record) => record.fetch_status === first);
    return uniform && first !== "success" ? first : null;
  };

  const unavailableColumnStates = new Map(
    sources.map((source) => [source, columnFetchState(source)]),
  );

  const statusDisplayRowBySource = new Map(
    sources.map((source) => [
      source,
      fields.find((field) => recordFor(field, source) !== undefined),
    ]),
  );

  const conflicted = new Set(
    fields.filter((field) =>
      evidence.some(
        (record) =>
          record.field === field &&
          record.fetch_status === "success" &&
          record.value_state === "conflict",
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
              <span className={styles.provenance} title="">
                imported
              </span>
              <span className={styles.provenance} title="">
                {fetchedLabel(importedAt)}
              </span>
            </div>
            {sources.map((source) => {
              const state = unavailableColumnStates.get(source);
              const sourceRecord = evidence.find(
                (record) => record.source === source,
              );
              const refreshable = isRefreshSource(source);
              const applicable =
                sourceRecord?.fetch_status !== "not_applicable";

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
                    {sourceRecord ? recordLabel(sourceRecord, shares) : "—"}
                  </span>
                  {sourceRecord?.fetch_status !== "not_applicable" && (
                    <span className={styles.provenance} title="">
                      {fetchedLabel(sourceRecord?.fetched_at ?? null)}
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
                {datasetByField[field] && (
                  <span className={`${styles.cellLine} ${styles.value}`}>
                    {datasetByField[field]}
                  </span>
                )}
              </div>
              {sources.map((source) => (
                <Cell
                  key={source}
                  record={recordFor(field, source)}
                  source={source}
                  field={field}
                  columnFetchState={unavailableColumnStates.get(source) ?? null}
                  showColumnStatus={
                    statusDisplayRowBySource.get(source) === field
                  }
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
  columnFetchState,
  showColumnStatus,
}: {
  record: EvidenceRecord | undefined;
  source: string;
  field: string;
  columnFetchState: SourceFetchStatus | null;
  showColumnStatus: boolean;
}) {
  const fetchState =
    columnFetchState ??
    (record?.fetch_status !== "success" ? record?.fetch_status : null);
  if (fetchState) {
    const broken = brokenFetches.includes(fetchState);

    return (
      <div
        role="cell"
        className={`${styles.cell} ${broken ? styles.cellBroken : styles.cellNever}`}
      >
        {!columnFetchState || showColumnStatus ? (
          <>
            <span className={styles.absence}>{fetchNotes[fetchState]}</span>
            {broken && (
              <span className={styles.reason}>no evidence returned</span>
            )}
          </>
        ) : (
          <span className={styles.srOnly}>
            {sourceLabel(source)} {fetchNotes[fetchState]}, {fieldName(field)}{" "}
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

  const absenceLabel =
    record.value_state === "missing" && field === "affiliation"
      ? "no affiliations found"
      : emptyWords[record.value_state];
  if (absenceLabel || record.value === null) {
    return (
      <div role="cell" className={styles.cell}>
        <span className={styles.cellLine}>
          <span className={styles.absence}>{absenceLabel ?? "absent"}</span>
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
      </span>
    </div>
  );
}
