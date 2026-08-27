import { buildReviewCase } from "../../test/data";
import { orderCases, readQueueSort, type QueueSortColumn } from "./ordering";

it.each<QueueSortColumn>([
  "score",
  "share",
  "candidates",
  "publications",
  "status",
])(
  "keeps deferred cases last when sorting by %s in either direction",
  (column) => {
    const pending = buildReviewCase({ id: "pending", priority_score: 20 });
    const deferred = buildReviewCase({
      id: "deferred",
      status: "deferred",
      priority_score: 99,
    });
    const cases = [deferred, pending];
    for (const direction of ["asc", "desc"] as const) {
      expect(orderCases(cases, column, direction).map(({ id }) => id)).toEqual([
        "pending",
        "deferred",
      ]);
    }
    expect(cases).toEqual([deferred, pending]);
  },
);

it("sorts within each status partition without disturbing ties", () => {
  const cases = [
    buildReviewCase({ id: "low", priority_score: 10 }),
    buildReviewCase({
      id: "deferred-low",
      status: "deferred",
      priority_score: 20,
    }),
    buildReviewCase({ id: "high", priority_score: 90 }),
    buildReviewCase({ id: "tie", priority_score: 90 }),
    buildReviewCase({
      id: "deferred-high",
      status: "deferred",
      priority_score: 80,
    }),
  ];
  expect(orderCases(cases, "score", "desc").map(({ id }) => id)).toEqual([
    "high",
    "tie",
    "low",
    "deferred-high",
    "deferred-low",
  ]);
  expect(orderCases(cases, null, "desc").map(({ id }) => id)).toEqual([
    "low",
    "high",
    "tie",
    "deferred-low",
    "deferred-high",
  ]);
});

it("ignores invalid and orphaned sort parameters", () => {
  expect(readQueueSort(new URLSearchParams("sort=score&dir=asc"))).toEqual({
    column: "score",
    direction: "asc",
  });
  expect(readQueueSort(new URLSearchParams("sort=invalid&dir=asc"))).toEqual({
    column: null,
    direction: "desc",
  });
  expect(readQueueSort(new URLSearchParams("dir=asc"))).toEqual({
    column: null,
    direction: "desc",
  });
});
