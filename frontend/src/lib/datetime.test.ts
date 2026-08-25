import {
  compactRelativeParts,
  formatFetchedAt,
  formatRelativeTime,
} from "./datetime";

const CURRENT_TIME = new Date("2026-08-25T18:00:00Z");

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(CURRENT_TIME);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("formatRelativeTime", () => {
  it.each([
    ["2026-08-25T17:59:45Z", "1 minute ago"],
    ["2026-08-25T15:00:00Z", "3 hours ago"],
    ["2026-08-17T18:00:00Z", "8 days ago"],
  ])("formats %s as %s", (timestamp, expected) => {
    expect(formatRelativeTime(timestamp)).toBe(expected);
  });
});

describe("compactRelativeParts", () => {
  it("returns an empty state when no timestamp is available", () => {
    expect(compactRelativeParts(null)).toEqual({ value: "—", unit: null });
  });

  it("uses compact units for available timestamps", () => {
    expect(compactRelativeParts("2026-08-23T18:00:00Z")).toEqual({
      value: "2",
      unit: "d",
    });
  });
});

it("leaves an invalid fetched timestamp visible", () => {
  expect(formatFetchedAt("not-a-date")).toBe("not-a-date");
});
