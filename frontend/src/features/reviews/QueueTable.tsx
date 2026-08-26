import { Link } from "react-router-dom";
import type { ValidationCase } from "../../api/types";
import Hint from "../../components/Hint";
import SortHeader from "../../components/SortHeader";
import type { SortDirection } from "../../components/SortHeader";
import { statusText } from "../../lib/decisions";
import { CANDIDATES_HINT, SCORE_HINT, SHARE_HINT } from "../../lib/hints";
import styles from "./QueuePage.module.css";

export type QueueSortColumn =
  | "score"
  | "share"
  | "candidates"
  | "publications"
  | "status";

export default function QueueTable({
  cases,
  loading,
  stale,
  rowSearch,
  sort,
  direction,
  onSort,
}: {
  cases: ValidationCase[];
  loading: boolean;
  stale: boolean;
  rowSearch: string;
  sort: QueueSortColumn | "";
  direction: SortDirection;
  onSort: (column: QueueSortColumn, direction: SortDirection | null) => void;
}) {
  return (
    <div className={styles.tableScroll}>
      <table
        role="table"
        aria-busy={loading}
        className={`${styles.table} ${stale ? styles.stale : ""}`}
      >
        <thead role="rowgroup">
          <tr role="row" className={styles.headerRow}>
            <th role="columnheader" scope="col">
              <span className={styles.srOnly}>position</span>
            </th>
            <th role="columnheader" scope="col">
              author
            </th>
            <th role="columnheader" scope="col" className={styles.hintHeader}>
              <SortHeader
                label="score"
                active={sort === "score"}
                direction={direction}
                clearable
                onSort={(next) => onSort("score", next)}
              />
              <Hint text={SCORE_HINT} />
            </th>
            <th role="columnheader" scope="col" className={styles.hintHeader}>
              <SortHeader
                label="top share"
                active={sort === "share"}
                direction={direction}
                clearable
                onSort={(next) => onSort("share", next)}
              >
                top share
              </SortHeader>
              <Hint text={SHARE_HINT} />
            </th>
            <th role="columnheader" scope="col" className={styles.hintHeader}>
              <SortHeader
                label="candidates"
                active={sort === "candidates"}
                direction={direction}
                clearable
                onSort={(next) => onSort("candidates", next)}
              />
              <Hint text={CANDIDATES_HINT} />
            </th>
            <th role="columnheader" scope="col">
              <SortHeader
                label="publications"
                active={sort === "publications"}
                direction={direction}
                clearable
                onSort={(next) => onSort("publications", next)}
              />
            </th>
            <th role="columnheader" scope="col">
              <SortHeader
                label="status"
                active={sort === "status"}
                direction={direction}
                clearable
                onSort={(next) => onSort("status", next)}
              />
            </th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {cases.map((reviewCase, index) => (
            <ReviewRow
              key={reviewCase.id}
              reviewCase={reviewCase}
              position={index + 1}
              search={rowSearch}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewRow({
  reviewCase,
  position,
  search,
}: {
  reviewCase: ValidationCase;
  position: number;
  search: string;
}) {
  return (
    <tr role="row" className={styles.reviewRow}>
      <td role="cell" className={styles.position}>
        {position}
      </td>
      <th role="rowheader" scope="row" className={styles.author} title="">
        <Link
          to={{ pathname: `/reviews/${reviewCase.id}`, search }}
          className={styles.reviewLink}
        >
          {reviewCase.target.author_name}
        </Link>
      </th>
      <td role="cell" className={styles.score}>
        {Math.round(reviewCase.priority_score)}
      </td>
      <td role="cell" className={styles.numericValue}>
        {reviewCase.detail.top_share === null
          ? "—"
          : `${Math.round(reviewCase.detail.top_share)}%`}
      </td>
      <td role="cell" className={styles.numericValue}>
        {reviewCase.detail.candidate_ids.length}
      </td>
      <td role="cell" className={styles.numericValue}>
        {reviewCase.affected_count}
      </td>
      <td role="cell" className={styles.status}>
        {statusText(reviewCase.status)}
      </td>
    </tr>
  );
}
