import { buildQueueSettings } from "../../test/data";
import {
  toFormValues,
  parseSettingsForm,
  normalizedWeightPercent,
  differsFromSaved,
} from "./settingsForm";

it("normalizes valid weights without treating zero as missing", () => {
  const settings = buildQueueSettings({
    weights: { publication_impact: 0, fragmentation: 1, cluster_ambiguity: 3 },
  });
  const values = toFormValues(settings);
  const parsed = parseSettingsForm(values);
  expect(parsed.eligibilityError).toBeNull();
  expect(parsed.weightsError).toBeNull();
  expect(normalizedWeightPercent(parsed.weights, "publication_impact")).toBe(
    "0.0",
  );
  expect(normalizedWeightPercent(parsed.weights, "cluster_ambiguity")).toBe(
    "75.0",
  );
  expect(differsFromSaved(values, settings)).toBe(false);
});

it.each([
  ["", "All multipliers are required"],
  ["-1", "Multipliers must be 0 or greater"],
  ["Infinity", "All multipliers are required"],
])("rejects multiplier %s", (weight, error) => {
  const values = toFormValues(buildQueueSettings());
  values.weights.publication_impact = weight;
  expect(parseSettingsForm(values)).toMatchObject({
    weights: null,
    weightsError: error,
  });
});

it("validates both sections independently", () => {
  const values = toFormValues(buildQueueSettings());
  values.maxTopCandidateShare = "101";
  values.weights = {
    publication_impact: "0",
    fragmentation: "0",
    cluster_ambiguity: "0",
  };
  expect(parseSettingsForm(values)).toMatchObject({
    eligibilityError: "Top share limit must be between 0 and 100",
    weightsError: "At least one multiplier must be greater than 0",
  });
});

it("rejects an overflowing multiplier total", () => {
  const values = toFormValues(buildQueueSettings());
  values.weights.publication_impact = "1e308";
  values.weights.fragmentation = "1e308";
  expect(parseSettingsForm(values).weightsError).toBe(
    "Multiplier total is too large",
  );
});
