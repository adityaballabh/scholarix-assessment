import { normalizeActivitySearch, readActivityFilters } from "./filters";

it("removes stale filters and orphan direction while retaining search", () => {
  const params = new URLSearchParams(
    "reviewer=Ghost&from=invalid&to=bad&since=old&sort=bad&dir=asc&query=Eric&note=clusters",
  );
  const normalized = normalizeActivitySearch(params, ["Adi"]);
  expect(normalized.toString()).toBe("query=Eric&note=clusters");
  expect(params.get("reviewer")).toBe("Ghost");
  expect(readActivityFilters(normalized)).toMatchObject({
    sort: "time",
    explicitSort: null,
    direction: "desc",
  });
});

it("waits for reviewers to load before discarding their filter", () => {
  const params = new URLSearchParams("reviewer=Adi&sort=reviewer&dir=asc");
  expect(normalizeActivitySearch(params).toString()).toBe(params.toString());
  expect(normalizeActivitySearch(params, ["Adi"]).toString()).toBe(
    params.toString(),
  );
  expect(normalizeActivitySearch(params, []).has("reviewer")).toBe(false);
});

it("preserves valid transition and time filters", () => {
  const params = new URLSearchParams(
    "from=pending&to=needs_split&since=7d&sort=time&dir=asc",
  );
  expect(readActivityFilters(normalizeActivitySearch(params))).toMatchObject({
    fromStatus: "pending",
    toStatus: "needs_split",
    since: "7d",
    direction: "asc",
  });
});
