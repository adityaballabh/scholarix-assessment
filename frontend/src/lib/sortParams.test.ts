import { updateSortParams } from "./sortParams";

it("updates sorting without dropping unrelated filters", () => {
  const current = new URLSearchParams("status=pending&sort=time&dir=asc");

  expect(updateSortParams(current, "score", "desc").toString()).toBe(
    "status=pending&sort=score",
  );
  expect(current.toString()).toBe("status=pending&sort=time&dir=asc");
});

it("clears sorting without dropping unrelated filters", () => {
  const current = new URLSearchParams("query=Larson&sort=score&dir=asc");

  expect(updateSortParams(current, "score", null).toString()).toBe(
    "query=Larson",
  );
});
