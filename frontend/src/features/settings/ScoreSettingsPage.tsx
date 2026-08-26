import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ApiError,
  getQueueSettings,
  rebuildQueue,
  updateQueueSettings,
} from "../../api/client";
import type {
  QueueSettings,
  QueueSettingsUpdate,
  PriorityWeights,
} from "../../api/types";
import Hint from "../../components/Hint";
import SectionRule from "../../components/SectionRule";
import { useToast } from "../../components/Toast";
import styles from "./ScoreSettingsPage.module.css";

const ELIGIBILITY_HINT =
  "previously displayed profiles that no longer meet this limit are archived";

type WeightKey = keyof PriorityWeights;

interface FormValues {
  maxTopCandidateShare: string;
  weights: Record<WeightKey, string>;
}

type ErrorScope = "eligibility" | "weights" | "form";

interface FieldError {
  scope: ErrorScope;
  message: string;
}

const WEIGHT_FIELDS: { key: WeightKey; label: string; term: string }[] = [
  { key: "publication_impact", label: "publications", term: "publications" },
  {
    key: "fragmentation",
    label: "fragmentation (100 − top share)",
    term: "fragmentation",
  },
  { key: "cluster_ambiguity", label: "candidates", term: "candidates" },
];

function formValues(config: QueueSettings): FormValues {
  return {
    maxTopCandidateShare: config.max_top_candidate_share.toString(),
    weights: {
      publication_impact: config.weights.publication_impact.toString(),
      fragmentation: config.weights.fragmentation.toString(),
      cluster_ambiguity: config.weights.cluster_ambiguity.toString(),
    },
  };
}

function parseValue(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getEligibilityError(values: FormValues): FieldError | null {
  const limit = parseValue(values.maxTopCandidateShare);
  return limit === null || limit < 0 || limit > 100
    ? {
        scope: "eligibility",
        message: "Top share limit must be between 0 and 100",
      }
    : null;
}

function getWeightsError(values: FormValues): FieldError | null {
  const weights = Object.values(values.weights).map(parseValue);
  if (weights.some((weight) => weight === null)) {
    return { scope: "weights", message: "All multipliers are required" };
  }
  if (weights.some((weight) => weight !== null && weight < 0)) {
    return { scope: "weights", message: "Multipliers must be 0 or greater" };
  }
  if (weights.reduce<number>((sum, weight) => sum + (weight ?? 0), 0) <= 0) {
    return {
      scope: "weights",
      message: "At least one multiplier must be greater than 0",
    };
  }
  return null;
}

function buildUpdate(
  values: FormValues,
  config: QueueSettings,
): QueueSettingsUpdate | FieldError {
  const eligibilityError = getEligibilityError(values);
  if (eligibilityError) return eligibilityError;

  const weightsError = getWeightsError(values);
  if (weightsError) return weightsError;

  const maxTopCandidateShare = parseValue(values.maxTopCandidateShare);
  const weights = {
    publication_impact: parseValue(values.weights.publication_impact),
    fragmentation: parseValue(values.weights.fragmentation),
    cluster_ambiguity: parseValue(values.weights.cluster_ambiguity),
  };
  const parsedWeights = weights as PriorityWeights;

  return {
    max_top_candidate_share: maxTopCandidateShare as number,
    weights: parsedWeights,
    expected_version: config.version,
  };
}

function checkErrors(
  values: FormValues,
  config: QueueSettings,
): FieldError | null {
  const result = buildUpdate(values, config);
  return "scope" in result ? result : null;
}

function differsFromSaved(values: FormValues, config: QueueSettings): boolean {
  return (
    parseValue(values.maxTopCandidateShare) !==
      config.max_top_candidate_share ||
    WEIGHT_FIELDS.some(
      ({ key }) => parseValue(values.weights[key]) !== config.weights[key],
    )
  );
}

function weightValue(values: FormValues, key: WeightKey): string {
  const weights = WEIGHT_FIELDS.map(({ key: weightKey }) =>
    parseValue(values.weights[weightKey]),
  );
  if (weights.some((weight) => weight === null || weight < 0)) return "";
  const total = weights.reduce<number>((sum, weight) => sum + (weight ?? 0), 0);
  if (total === 0) return "";
  const weight = parseValue(values.weights[key]) ?? 0;
  return ((weight / total) * 100).toFixed(1);
}

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
  const [actionError, setActionError] = useState<FieldError | null>(null);
  const [busy, setBusy] = useState(false);
  const [savedForRebuild, setSavedForRebuild] = useState(true);

  useEffect(() => {
    let active = true;
    getQueueSettings()
      .then((loaded) => {
        if (!active) return;
        setConfig(loaded);
        setValues(formValues(loaded));
      })
      .catch(() => {
        if (active) setLoadError(true);
      });
    return () => {
      active = false;
    };
  }, []);

  function updateWeight(key: WeightKey, value: string) {
    if (!values || !config) return;
    const next = { ...values, weights: { ...values.weights, [key]: value } };
    setValues(next);
    setSavedForRebuild(false);
    setActionError(null);
  }

  async function saveAndRebuildQueue() {
    if (!config || !values || busy) return;
    const update = buildUpdate(values, config);
    if ("scope" in update) {
      setActionError(update);
      return;
    }

    setBusy(true);
    setActionError(null);
    let settingsSaved = savedForRebuild;
    try {
      if (!savedForRebuild) {
        const saved = await updateQueueSettings(update);
        setConfig(saved);
        setValues(formValues(saved));
        setSavedForRebuild(true);
        settingsSaved = true;
      }
      await rebuildQueue();
      showToast("Queue settings saved and queue rebuilt.");
      navigate(returnTo, { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setActionError({
          scope: "form",
          message: "Queue settings changed elsewhere — reload and try again",
        });
      } else if (settingsSaved) {
        setActionError({
          scope: "form",
          message: "Settings are saved, but the queue could not be rebuilt",
        });
      } else {
        setActionError({
          scope: "form",
          message: "Queue settings could not be saved",
        });
      }
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <p className={styles.pageState}>Queue settings could not be loaded</p>
    );
  }
  if (!config || !values) {
    return <p className={styles.pageState}>Loading queue settings…</p>;
  }

  const dirty = differsFromSaved(values, config);
  const eligibilityError = getEligibilityError(values);
  const weightsError = getWeightsError(values);
  const valid = checkErrors(values, config) === null;

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
                  profiles at or below this enter the queue
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
                value={values.maxTopCandidateShare}
                onChange={(event) => {
                  const next = {
                    ...values,
                    maxTopCandidateShare: event.target.value,
                  };
                  setValues(next);
                  setSavedForRebuild(false);
                  setActionError(null);
                }}
              />
              <span>%</span>
            </span>
          </div>
          {eligibilityError && (
            <p className={styles.rowError} role="alert">
              {eligibilityError.message}
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
                  value={values.weights[key]}
                  onChange={(event) => updateWeight(key, event.target.value)}
                />
              </span>
              <span className={styles.termText}>
                <span className={styles.operator}>
                  {index === 0 ? "" : "+"}
                </span>
                <span className={styles.termShare}>
                  {weightValue(values, key)}
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
            max is computed across all authors currently in the queue
          </p>
          {(weightsError || actionError?.scope === "form") && (
            <p className={styles.rowError} role="alert">
              {weightsError?.message ?? actionError?.message}
            </p>
          )}
        </fieldset>

        <div className={styles.actions}>
          {dirty && (
            <button
              type="button"
              className={styles.reset}
              disabled={busy}
              onClick={() => {
                setValues(formValues(config));
                setSavedForRebuild(true);
                setActionError(null);
              }}
            >
              revert
            </button>
          )}
          <button
            type="button"
            className={styles.cancel}
            disabled={busy}
            onClick={() => navigate(returnTo)}
          >
            cancel
          </button>
          <button
            type="submit"
            className={styles.primary}
            disabled={busy || !dirty || !valid}
          >
            save and rebuild queue
          </button>
        </div>
      </form>
    </section>
  );
}
