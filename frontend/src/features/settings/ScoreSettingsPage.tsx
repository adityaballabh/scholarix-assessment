import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ApiError,
  getQueueSettings,
  rebuildQueue,
  updateQueueSettings,
} from "../../api/client";
import type { QueueSettings } from "../../api/types";
import {
  WEIGHT_FIELDS,
  toFormValues,
  parseSettingsForm,
  differsFromSaved,
  normalizedWeightPercent,
  type WeightKey,
  type FormValues,
} from "./settingsForm";
import Hint from "../../components/Hint";
import SectionRule from "../../components/SectionRule";
import { useToast } from "../../components/Toast";
import styles from "./ScoreSettingsPage.module.css";

const ELIGIBILITY_HINT =
  "Previously queued profiles above this limit are archived";

export default function ScoreSettingsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const showToast = useToast();
  const state = location.state as { returnTo?: string } | null;
  const returnTo = state?.returnTo?.startsWith("/reviews")
    ? state.returnTo
    : "/reviews";
  const [config, setConfig] = useState<QueueSettings | null>(null);
  const [values, setValues] = useState<FormValues | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rebuildPending, setRebuildPending] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setLoadError(false);
    getQueueSettings()
      .then((loaded) => {
        if (!active) return;
        setConfig(loaded);
        setValues(toFormValues(loaded));
      })
      .catch(() => {
        if (active) setLoadError(true);
      });
    return () => {
      active = false;
    };
  }, [loadAttempt]);

  function updateWeight(key: WeightKey, value: string) {
    if (!values || !config) return;
    const next = { ...values, weights: { ...values.weights, [key]: value } };
    setValues(next);
    setActionError(null);
  }

  async function saveAndRebuildQueue() {
    if (!config || !values || busy) return;
    const parsed = parseSettingsForm(values);
    if (
      parsed.eligibilityError ||
      !parsed.weights ||
      parsed.maxTopCandidateShare === null
    )
      return;
    const dirty = differsFromSaved(values, config);
    if (!dirty && !rebuildPending) return;

    setBusy(true);
    setActionError(null);
    let settingsSaved = !dirty && rebuildPending;
    try {
      if (dirty) {
        const saved = await updateQueueSettings({
          max_top_candidate_share: parsed.maxTopCandidateShare,
          weights: parsed.weights,
          expected_version: config.version,
        });
        setConfig(saved);
        setValues(toFormValues(saved));
        setRebuildPending(true);
        settingsSaved = true;
      }
      await rebuildQueue();
      setRebuildPending(false);
      showToast("Settings saved and queue rebuilt");
      navigate(returnTo, { replace: true });
    } catch (error) {
      setActionError(
        error instanceof ApiError && error.status === 409
          ? "Queue settings changed elsewhere. Reload and try again"
          : settingsSaved
            ? "Settings saved. Could not rebuild the queue"
            : "Could not save queue settings",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <p className={styles.pageState} role="alert">
        Could not load queue settings{" "}
        <button
          type="button"
          onClick={() => setLoadAttempt((attempt) => attempt + 1)}
        >
          retry
        </button>
      </p>
    );
  }
  if (!config || !values) {
    return <p className={styles.pageState}>Loading queue settings…</p>;
  }

  const dirty = differsFromSaved(values, config);
  const { eligibilityError, weightsError, weights } = parseSettingsForm(values);
  const valid = !eligibilityError && !weightsError;

  return (
    <section className={styles.page}>
      <button
        type="button"
        className={styles.back}
        disabled={busy}
        onClick={() => navigate(returnTo)}
      >
        ← back to queue
      </button>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void saveAndRebuildQueue();
        }}
      >
        <fieldset className={styles.group} disabled={busy}>
          <SectionRule label="Review Eligibility" />
          <div className={styles.row}>
            <span className={styles.rowText}>
              <label className={styles.rowLabel} htmlFor="top-share-limit">
                top share limit
              </label>
              <span className={styles.inlineHint}>
                <span className={styles.rowNote}>
                  profiles at or below this limit enter the queue
                </span>
                <Hint text={ELIGIBILITY_HINT} />
              </span>
            </span>
            <span className={styles.control}>
              <input
                id="top-share-limit"
                className={styles.input}
                type="number"
                min="0"
                max="100"
                step="0.1"
                aria-invalid={!!eligibilityError}
                aria-describedby={
                  eligibilityError ? "eligibility-error" : undefined
                }
                value={values.maxTopCandidateShare}
                onChange={(event) => {
                  const next = {
                    ...values,
                    maxTopCandidateShare: event.target.value,
                  };
                  setValues(next);
                  setActionError(null);
                }}
              />
              <span>%</span>
            </span>
          </div>
          {eligibilityError && (
            <p id="eligibility-error" className={styles.rowError} role="alert">
              {eligibilityError}
            </p>
          )}
        </fieldset>

        <fieldset className={styles.group} disabled={busy}>
          <div className={styles.scoreRule}>
            <SectionRule
              label="Score Computation"
              hint="multipliers normalized to 100%"
            />
          </div>
          {WEIGHT_FIELDS.map(({ key, label, term }, index) => (
            <label className={`${styles.row} ${styles.weightRow}`} key={key}>
              <span className={styles.rowLabel}>{label}</span>
              <span className={styles.control}>
                <input
                  className={styles.input}
                  type="number"
                  min="0"
                  step="0.1"
                  aria-invalid={!!weightsError}
                  aria-describedby={weightsError ? "weights-error" : undefined}
                  value={values.weights[key]}
                  onChange={(event) => updateWeight(key, event.target.value)}
                />
              </span>
              <span className={styles.termText}>
                <span className={styles.operator}>
                  {index === 0 ? "" : "+"}
                </span>
                <span className={styles.termShare}>
                  {normalizedWeightPercent(weights, key)}
                </span>
                <span className={styles.formulaText}>
                  <span className={styles.multiply}>×</span>
                  <span className={styles.formulaBody}>
                    {term} / max {term}
                  </span>
                </span>
              </span>
            </label>
          ))}
          <p className={styles.scoreNote}>
            max is the highest value among authors in the current queue
          </p>
          {weightsError && (
            <p id="weights-error" className={styles.rowError} role="alert">
              {weightsError}
            </p>
          )}
        </fieldset>

        {actionError && (
          <p className={styles.rowError} role="alert">
            {actionError}
          </p>
        )}
        <div className={styles.actions}>
          {dirty && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setValues(toFormValues(config));
                setActionError(null);
              }}
            >
              revert
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => navigate(returnTo)}
          >
            cancel
          </button>
          <button
            type="submit"
            className={styles.primary}
            disabled={busy || (!dirty && !rebuildPending) || !valid}
          >
            {rebuildPending && !dirty
              ? "retry rebuild"
              : "save and rebuild queue"}
          </button>
        </div>
      </form>
    </section>
  );
}
