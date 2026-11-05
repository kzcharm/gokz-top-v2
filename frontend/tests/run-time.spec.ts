import { expect, test } from "@playwright/test"
import { formatRunTime } from "../src/lib/run-time"

test("Run times retain millisecond precision and hour boundaries", () => {
  for (const [seconds, precise, whole] of [
    [0, "0:00.000", "0:00"],
    [9.007, "0:09.007", "0:09"],
    [83.456, "1:23.456", "1:23"],
    [59.9996, "1:00.000", "1:00"],
    [3599.9996, "1:00:00.000", "1:00:00"],
    [3723.004, "1:02:03.004", "1:02:03"],
    [-1, "0:00.000", "0:00"],
  ] as const) {
    expect(formatRunTime(seconds)).toBe(precise)
    expect(formatRunTime(seconds, false)).toBe(whole)
  }
  expect(formatRunTime(Number.NaN)).toBe("—")
  expect(formatRunTime(Number.POSITIVE_INFINITY)).toBe("—")
})
