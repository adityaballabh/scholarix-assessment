import { Link } from "react-router-dom";
import type { AuthorIdentityDetail } from "../../api/types";
import SectionRule from "../../components/SectionRule";
import { countedNoun } from "./labels";
import { leadTitle, yearSpan } from "./years";
import styles from "./Identity.module.css";

const CANDIDATE_PREVIEW = 3;

export default function Identity({
  detail,
  caseId,
  search,
}: {
  detail: AuthorIdentityDetail;
  caseId: string;
  search: string;
}) {
  const { candidate_ids, profile_topics } = detail;
  const preview = candidate_ids.slice(0, CANDIDATE_PREVIEW);
  const truncated = candidate_ids.length > preview.length;
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
          <div
            role="table"
            aria-label="Semantic Scholar candidate author IDs"
            className={styles.candidates}
          >
            <div role="rowgroup">
              <div role="row" className={`${styles.candidateRow} ${styles.head}`}>
                <span role="columnheader">
                  <span className={styles.srOnly}>position</span>
                </span>
                <span role="columnheader">s2 id</span>
                <span role="columnheader">share</span>
                <span role="columnheader">years</span>
                <span role="columnheader">most recent publication</span>
              </div>
            </div>
            <div role="rowgroup">
              {preview.map((candidate, index) => (
                <div role="row" className={styles.candidateRow} key={candidate.id}>
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
                  <span role="cell" className={styles.title}>
                    {leadTitle(candidate)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {profile_topics.length > 0 && (
        <>
          <SectionRule label="Profile Topics" hint="from Scholarix" />
          <ul className={styles.topics}>
            {profile_topics.map((topic) => (
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
