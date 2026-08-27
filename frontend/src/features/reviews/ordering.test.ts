import { buildReviewCase } from "../../test/data";
import type { ReviewStatus } from "../../api/types";
import { orderCases, readQueueSort, type QueueSortColumn } from "./ordering";

it.each<QueueSortColumn>([
  "score",
  "share",
  "candidates",
  "publications",
  "status",
])(
  "includes deferred cases in the selected %s order in either direction",
  (column) => {
    const pending = buildReviewCase({
      id: "pending",
      priority_score: 20,
      affected_count: 10,
    });
    const deferred = buildReviewCase({
      id: "deferred",
      status: "deferred",
      priority_score: 99,
      affected_count: 20,
      detail: {
        ...pending.detail,
        top_share: 75,
        candidate_ids: [
          ...pending.detail.candidate_ids,
          { ...pending.detail.candidate_ids[0], id: "39673102" },
        ],
      },
    });
    const cases = [deferred, pending];
    expect(orderCases(cases, column, "asc").map(({ id }) => id)).toEqual([
      "pending",
      "deferred",
    ]);
    expect(orderCases(cases, column, "desc").map(({ id }) => id)).toEqual([
      "deferred",
      "pending",
    ]);
    expect(cases).toEqual([deferred, pending]);
  },
);

it("uses score ordering by default without pushing deferred cases to the end", () => {
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
    "deferred-high",
    "deferred-low",
    "low",
  ]);
  expect(orderCases(cases, null, "desc").map(({ id }) => id)).toEqual([
    "high",
    "tie",
    "deferred-high",
    "deferred-low",
    "low",
  ]);
});

function sortableCase(
  id: string,
  score: number,
  share: number | null,
  candidates: number,
  publications: number,
  status: ReviewStatus,
) {
  const reviewCase = buildReviewCase({
    id,
    priority_score: score,
    affected_count: publications,
    status,
  });
  reviewCase.detail = {
    ...reviewCase.detail,
    top_share: share,
    candidate_ids: Array.from({ length: candidates }, (_, index) => ({
      ...reviewCase.detail.candidate_ids[0],
      id: String(index),
    })),
  };
  return reviewCase;
}

it("breaks ties by column order and case ID after an explicit sort", () => {
  const cases = [
    sortableCase("case-b", 80, 60, 2, 10, "needs_split"),
    sortableCase("case-a", 80, 60, 2, 10, "needs_split"),
    sortableCase("case-v", 80, 60, 2, 10, "one_author"),
    sortableCase("case-w", 80, 60, 2, 20, "deferred"),
    sortableCase("case-x", 80, 60, 3, 10, "deferred"),
    sortableCase("case-y", 80, 70, 1, 10, "deferred"),
    sortableCase("case-z", 90, 10, 1, 10, "deferred"),
  ];
  expect(orderCases(cases, null, "desc").map(({ id }) => id)).toEqual([
    "case-z",
    "case-y",
    "case-x",
    "case-w",
    "case-v",
    "case-a",
    "case-b",
  ]);
  expect(orderCases(cases, "publications", "asc").map(({ id }) => id)).toEqual([
    "case-z",
    "case-y",
    "case-x",
    "case-v",
    "case-a",
    "case-b",
    "case-w",
  ]);
  expect(orderCases(cases, "publications", "desc").map(({ id }) => id)).toEqual(
    ["case-w", "case-z", "case-y", "case-x", "case-v", "case-a", "case-b"],
  );
  expect(orderCases(cases, "score", "asc").map(({ id }) => id)).toEqual([
    "case-y",
    "case-x",
    "case-w",
    "case-v",
    "case-a",
    "case-b",
    "case-z",
  ]);
});

it("treats a missing top share as zero before comparing candidates", () => {
  const cases = [
    sortableCase("case-a", 50, null, 0, 10, "pending"),
    sortableCase("case-b", 50, 0, 1, 10, "pending"),
  ];
  expect(orderCases(cases, null, "desc").map(({ id }) => id)).toEqual([
    "case-b",
    "case-a",
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
