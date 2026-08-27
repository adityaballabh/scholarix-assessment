import type { PriorityWeights, QueueSettings } from "../../api/types";

export type WeightKey = keyof PriorityWeights;

export interface FormValues {
  maxTopCandidateShare: string;
  weights: Record<WeightKey, string>;
}

export const WEIGHT_FIELDS: { key: WeightKey; label: string; term: string }[] =
  [
    { key: "publication_impact", label: "publications", term: "publications" },
    {
      key: "fragmentation",
      label: "fragmentation (100 − top share)",
      term: "fragmentation",
    },
    { key: "cluster_ambiguity", label: "candidates", term: "candidates" },
  ];

export function toFormValues(settings: QueueSettings): FormValues {
  return {
    maxTopCandidateShare: String(settings.max_top_candidate_share),
    weights: {
      publication_impact: String(settings.weights.publication_impact),
      fragmentation: String(settings.weights.fragmentation),
      cluster_ambiguity: String(settings.weights.cluster_ambiguity),
    },
  };
}

function parseNumber(value: string): number | null {
  if (!value.trim()) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function parseSettingsForm(values: FormValues): {
  maxTopCandidateShare: number | null;
  weights: PriorityWeights | null;
  eligibilityError: string | null;
  weightsError: string | null;
} {
  const maxTopCandidateShare = parseNumber(values.maxTopCandidateShare);
  const eligibilityError =
    maxTopCandidateShare === null ||
    maxTopCandidateShare < 0 ||
    maxTopCandidateShare > 100
      ? "Top share limit must be between 0 and 100"
      : null;
  const publicationImpact = parseNumber(values.weights.publication_impact);
  const fragmentation = parseNumber(values.weights.fragmentation);
  const clusterAmbiguity = parseNumber(values.weights.cluster_ambiguity);
  let weights: PriorityWeights | null = null;
  let weightsError: string | null = null;

  if (
    publicationImpact === null ||
    fragmentation === null ||
    clusterAmbiguity === null
  ) {
    weightsError = "All multipliers are required";
  } else if (
    publicationImpact < 0 ||
    fragmentation < 0 ||
    clusterAmbiguity < 0
  ) {
    weightsError = "Multipliers must be 0 or greater";
  } else if (publicationImpact + fragmentation + clusterAmbiguity === 0) {
    weightsError = "At least one multiplier must be greater than 0";
  } else if (
    !Number.isFinite(publicationImpact + fragmentation + clusterAmbiguity)
  ) {
    weightsError = "Multiplier total is too large";
  } else {
    weights = {
      publication_impact: publicationImpact,
      fragmentation,
      cluster_ambiguity: clusterAmbiguity,
    };
  }
  return { maxTopCandidateShare, weights, eligibilityError, weightsError };
}

export function differsFromSaved(
  values: FormValues,
  settings: QueueSettings,
): boolean {
  return (
    parseNumber(values.maxTopCandidateShare) !==
      settings.max_top_candidate_share ||
    WEIGHT_FIELDS.some(
      ({ key }) => parseNumber(values.weights[key]) !== settings.weights[key],
    )
  );
}

export function normalizedWeightPercent(
  weights: PriorityWeights | null,
  key: WeightKey,
): string {
  if (!weights) return "";
  const total =
    weights.publication_impact +
    weights.fragmentation +
    weights.cluster_ambiguity;
  return ((weights[key] / total) * 100).toFixed(1);
}
