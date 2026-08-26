import { Link } from "react-router-dom";
import type { AuthorIdentityDetail } from "../../api/types";
import Hint from "../../components/Hint";
import SectionRule from "../../components/SectionRule";
import { countedNoun } from "./labels";
import { leadTitle, yearSpan } from "./years";
import styles from "./Identity.module.css";

const CANDIDATE_PREVIEW = 3;

export default function Identity({
  detail,
  affectedCount,
  caseId,
  search,
}: {
  detail: AuthorIdentityDetail;
  affectedCount: number;
  caseId: string;
  search: string;
}) {
  const { candidate_ids, openalex_topics } = detail;
  const preview = candidate_ids.slice(0, CANDIDATE_PREVIEW);
  const truncated = candidate_ids.length > preview.length;
  const matched = candidate_ids.reduce(
    (total, candidate) => total + candidate.publications.length,
    0,
  );
  const previewLabel = `Top ${countedNoun(preview.length, "S2 ID", "S2 IDs")}`;

  return (
    <>
      {candidate_ids.length > 0 && (
        <>
          <SectionRule
            label={previewLabel}
            hint={
              truncated && (
                <Link
                  to={{ pathname: `/reviews/${caseId}/ids`, search }}
                  className={styles.seeAll}
                >
                  see all {candidate_ids.length}
                </Link>
              )
            }
          />
          <div className={styles.scroll}>
            <div
              role="table"
              aria-label="Semantic Scholar candidate author IDs"
              className={styles.candidates}
            >
              <div role="rowgroup">
                <div
                  role="row"
                  className={`${styles.candidateRow} ${styles.head}`}
                >
                  <span role="columnheader">
                    <span className={styles.srOnly}>position</span>
                  </span>
                  <span role="columnheader">S2 ID</span>
                  <span role="columnheader" className={styles.shareHeader}>
                    share
                    <Hint
                      text={`Share is based on the ${matched} publications matching an S2 ID out of ${affectedCount} total`}
                    />
                  </span>
                  <span role="columnheader">years</span>
                  <span role="columnheader">most recent publication</span>
                </div>
              </div>
              <div role="rowgroup">
                {preview.map((candidate, index) => (
                  <div
                    role="row"
                    className={styles.candidateRow}
                    key={candidate.id}
                  >
                    <span role="cell" className={styles.position}>
                      {index + 1}
                    </span>
                    <span role="cell" className={styles.identifier}>
                      {candidate.id}
                    </span>
                    <span role="cell" className={styles.share}>
                      {candidate.share.toFixed(1)}%
                    </span>
                    <span role="cell" className={styles.span}>
                      {yearSpan(candidate) ?? "—"}
                    </span>
                    <span role="cell" className={styles.title} title="">
                      {leadTitle(candidate)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {openalex_topics.length > 0 && (
        <>
          <SectionRule label="OpenAlex Topics" />
          <ul className={styles.topics}>
            {openalex_topics.map((topic) => (
              <li className={styles.topic} key={topic}>
                {topic}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
