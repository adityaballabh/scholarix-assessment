import { listCases, postDecision, setUnauthorizedHandler } from "./client";
import {
  AUTHOR_NAME,
  CASE_ID,
  buildActivityEvent,
  buildReviewCase,
} from "../test/data";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  setUnauthorizedHandler(null);
});

it("serializes case filters and includes credentials", async () => {
  const reviewCase = buildReviewCase();
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse([reviewCase]));
  vi.stubGlobal("fetch", fetchMock);

  await expect(
    listCases({
      status: ["pending", "deferred"],
      scope: "active",
      query: AUTHOR_NAME,
    }),
  ).resolves.toEqual([reviewCase]);

  expect(fetchMock).toHaveBeenCalledWith(
    "/api/cases?status=pending%2Cdeferred&scope=active&query=Eric+R.+Larson",
    { credentials: "include" },
  );
});

it("sends only the decision payload expected by the API", async () => {
  const event = buildActivityEvent();
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(event));
  vi.stubGlobal("fetch", fetchMock);

  await expect(
    postDecision({
      case_id: CASE_ID,
      action: "flag_for_split",
      note: event.note ?? undefined,
      expected_version: 3,
    }),
  ).resolves.toEqual(event);

  expect(fetchMock).toHaveBeenCalledWith(
    `/api/cases/${CASE_ID}/decisions`,
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      body: JSON.stringify({
        action: "flag_for_split",
        note: event.note,
        expected_version: 3,
      }),
    }),
  );
});

it("retries an unauthorized write after sign-in", async () => {
  const event = buildActivityEvent();
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse({ detail: "Not authenticated" }, 401))
    .mockResolvedValueOnce(jsonResponse(event));
  const signIn = vi.fn().mockResolvedValue(true);
  vi.stubGlobal("fetch", fetchMock);
  setUnauthorizedHandler(signIn);

  await expect(
    postDecision({
      case_id: CASE_ID,
      action: "flag_for_split",
      expected_version: 3,
    }),
  ).resolves.toEqual(event);

  expect(signIn).toHaveBeenCalledOnce();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("surfaces API error details", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(jsonResponse({ detail: "Case changed" }, 409)),
  );

  await expect(listCases()).rejects.toMatchObject({
    status: 409,
    message: "Case changed",
  });
});
