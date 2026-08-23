import type { ValidationCase } from "../../api/types";
import styles from "./CaseMeta.module.css";

export default function CaseMeta({
  reviewCase,
}: {
  reviewCase: ValidationCase;
}) {
  return (
    <div className={styles.meta}>
      <Meta label="case" value={reviewCase.id.replace(/^c-/, "#")} />
      <Meta
        label="score"
        value={Math.round(reviewCase.priority_score).toString()}
      />
      <Meta label="status" value={reviewCase.status.replace(/_/g, " ")} />
      {!reviewCase.queue_eligible && <Meta label="queue" value="archived" />}
      <Meta
        label="affected"
        value={`${reviewCase.affected_count.toLocaleString()} publications`}
      />
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <span className={styles.metaItem}>
      <span className={styles.metaLabel}>{label}</span>
      <span className={styles.metaValue}>{value}</span>
    </span>
  );
}
