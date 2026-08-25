import {
  defaultStatusForScope,
  readCaseFilters,
  readQueueScope,
} from "./filters";

describe("readCaseFilters", () => {
  it("defaults the active queue to pending cases", () => {
    expect(readCaseFilters(new URLSearchParams())).toEqual({
      query: undefined,
      scope: "active",
      status: "pending",
    });
  });

  it("defaults the archived queue to every state", () => {
    expect(readCaseFilters(new URLSearchParams("scope=archived"))).toEqual({
      query: undefined,
      scope: "archived",
      status: undefined,
    });
  });

  it("preserves valid filters and replaces an invalid status", () => {
    const valid = new URLSearchParams(
      "scope=archived&status=needs_split&query=Larson",
    );
    const invalid = new URLSearchParams("scope=active&status=unknown");

    expect(readCaseFilters(valid)).toEqual({
      query: "Larson",
      scope: "archived",
      status: "needs_split",
    });
    expect(readCaseFilters(invalid).status).toBe("pending");
  });
});

it("normalizes unknown queue scopes", () => {
  expect(readQueueScope("unknown")).toBe("active");
  expect(defaultStatusForScope("active")).toBe("pending");
});
