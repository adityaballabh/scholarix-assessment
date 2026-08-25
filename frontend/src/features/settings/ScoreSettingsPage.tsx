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

const WEIGHT_FIELDS: { key: WeightKey; label: string }[] = [
  { key: "publication_impact", label: "publications" },
  { key: "fragmentation", label: "fragmentation (100 − top share)" },
  { key: "cluster_ambiguity", label: "candidates" },
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

function buildUpdate(
  values: FormValues,
  config: QueueSettings,
): QueueSettingsUpdate | FieldError {
  const maxTopCandidateShare = parseValue(values.maxTopCandidateShare);
  if (
    maxTopCandidateShare === null ||
    maxTopCandidateShare < 0 ||
    maxTopCandidateShare > 100
  ) {
    return {
      scope: "eligibility",
      message: "Top share limit must be between 0 and 100",
    };
  }

  const weights = {
    publication_impact: parseValue(values.weights.publication_impact),
    fragmentation: parseValue(values.weights.fragmentation),
    cluster_ambiguity: parseValue(values.weights.cluster_ambiguity),
  };
  if (Object.values(weights).some((weight) => weight === null || weight < 0)) {
    return { scope: "weights", message: "Multipliers must be 0 or greater" };
  }
  const parsedWeights = weights as PriorityWeights;
  if (
    Object.values(parsedWeights).reduce((sum, weight) => sum + weight, 0) <= 0
  ) {
    return {
      scope: "weights",
      message: "At least one multiplier must be greater than 0",
    };
  }

  return {
    max_top_candidate_share: maxTopCandidateShare,
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

function weightShare(values: FormValues, key: WeightKey): string {
  const weights = WEIGHT_FIELDS.map(({ key: weightKey }) =>
    parseValue(values.weights[weightKey]),
  );
  if (weights.some((weight) => weight === null || weight < 0)) return "—";
  const total = weights.reduce<number>((sum, weight) => sum + (weight ?? 0), 0);
  if (total === 0) return "—";
  const weight = parseValue(values.weights[key]) ?? 0;
  return `${((weight / total) * 100).toFixed(1)}%`;
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
    setActionError(value.trim() === "" ? null : checkErrors(next, config));
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
                  setActionError(
                    event.target.value.trim() === ""
                      ? null
                      : checkErrors(next, config),
                  );
                }}
              />
              <span>%</span>
            </span>
          </div>
          {actionError?.scope === "eligibility" && (
            <p className={styles.rowError} role="alert">
              {actionError.message}
            </p>
          )}
        </fieldset>

        <fieldset className={styles.group} disabled={busy}>
          <SectionRule
            label="Score Rates"
            hint="multipliers, normalized to 100%"
          />
          {WEIGHT_FIELDS.map(({ key, label }) => (
            <label className={styles.row} key={key}>
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
                <span className={styles.share}>{weightShare(values, key)}</span>
              </span>
            </label>
          ))}
          {actionError && actionError.scope !== "eligibility" && (
            <p className={styles.rowError} role="alert">
              {actionError.message}
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
