import { expect, type Page, test } from "@playwright/test"

const STORAGE_KEY = "gokz-maps-last-visited-at"
const NOW = Date.parse("2026-10-20T12:00:00Z")
const BASELINE = "2026-10-19T12:00:00.000Z"

test.use({ storageState: { cookies: [], origins: [] } })

function makeMap(createdOn: string, validated = true) {
  return {
    id: 980001,
    name: "kz_notification_test",
    filesize: 1000,
    validated,
    tiers: { OVR: 1, KZT: 1, SKZ: 1, VNL: 1 },
    created_on: createdOn,
    updated_on: new Date(NOW).toISOString(),
    approved_by_steamid64: "76561198000000001",
    synced_at: new Date(NOW).toISOString(),
    authors: [],
    no_steamid_names: [],
  }
}

function mapsDot(page: Page) {
  return page
    .getByRole("link", { name: "Maps", exact: true })
    .locator('span[aria-hidden="true"].bg-red-500')
}

async function baseline(page: Page, value = BASELINE) {
  await page.addInitScript(
    ({ key, initialValue }) => {
      if (localStorage.getItem(key) === null) {
        localStorage.setItem(key, initialValue)
      }
    },
    { key: STORAGE_KEY, initialValue: value },
  )
}

async function mockMaps(page: Page, initialMaps: ReturnType<typeof makeMap>[]) {
  const state = { maps: initialMaps, fail: false, checks: [] as URL[] }
  await page.clock.install({ time: NOW })
  await page.context().route("**/v1/**", async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === "/v1/maps") {
      const since = url.searchParams.get("created_since")
      if (since) {
        state.checks.push(url)
        if (state.fail) {
          await route.fulfill({ status: 503, json: { detail: "Unavailable" } })
          return
        }
      }
      const maps = state.maps.filter(
        (map) =>
          (!since || Date.parse(map.created_on) >= Date.parse(since)) &&
          (url.searchParams.get("is_validated") !== "true" || map.validated),
      )
      await route.fulfill({
        json: maps.slice(0, Number(url.searchParams.get("limit") ?? 100)),
      })
      return
    }
    await route.fulfill({
      json:
        url.pathname === "/v1/maps/wrs" ||
        url.pathname === "/v1/leaderboards/maps"
          ? []
          : { data: [], count: 0 },
    })
  })
  return state
}

test("fresh and invalid baselines start quietly and persist", async ({
  page,
}) => {
  await baseline(page, "invalid")
  const state = await mockMaps(page, [makeMap(BASELINE)])
  await page.goto("/servers")
  await expect.poll(() => state.checks.length).toBeGreaterThan(0)
  await expect(mapsDot(page)).toHaveCount(0)
  const saved = await page.evaluate(
    (key) => localStorage.getItem(key),
    STORAGE_KEY,
  )
  expect(Date.parse(saved!)).toBeGreaterThanOrEqual(NOW)
  await page.reload()
  await expect(mapsDot(page)).toHaveCount(0)
  expect(
    await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY),
  ).toBe(saved)
})

test("missing baseline starts quietly", async ({ page }) => {
  const state = await mockMaps(page, [makeMap(BASELINE)])
  await page.goto("/servers")
  await expect.poll(() => state.checks.length).toBeGreaterThan(0)
  await expect(mapsDot(page)).toHaveCount(0)
  expect(
    await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY),
  ).not.toBeNull()
})

test("new approved maps notify, a catalog visit clears, and later maps notify again", async ({
  page,
}) => {
  await baseline(page)
  const state = await mockMaps(page, [makeMap("2026-10-20T10:00:00Z")])
  await page.goto("/servers")
  await expect(mapsDot(page)).toBeVisible()
  const query = state.checks[0].searchParams
  expect(query.get("is_validated")).toBe("true")
  expect(query.get("limit")).toBe("1")
  expect(query.get("created_since")).toBe("2026-10-19T12:00:00.001Z")
  expect(query.has("updated_since")).toBe(false)

  await page.getByRole("link", { name: "Maps", exact: true }).click()
  await expect(page).toHaveURL(/\/maps$/)
  await page.getByRole("link", { name: "Servers", exact: true }).click()
  await expect(mapsDot(page)).toHaveCount(0)
  await page.reload()
  await expect
    .poll(() => state.checks.at(-1)?.searchParams.get("created_since"))
    .not.toBe(query.get("created_since"))
  await expect(mapsDot(page)).toHaveCount(0)

  state.maps = [makeMap(new Date(NOW + 30_000).toISOString())]
  await page.clock.fastForward(60_000)
  await expect(mapsDot(page)).toBeVisible()
})

for (const scenario of [
  {
    name: "new unapproved map",
    maps: [makeMap("2026-10-20T10:00:00Z", false)],
  },
  {
    name: "old map invalidation",
    maps: [makeMap("2026-01-01T00:00:00Z", false)],
  },
  {
    name: "old map reapproval or metadata update",
    maps: [makeMap("2026-01-01T00:00:00Z")],
  },
  { name: "creation exactly at the baseline", maps: [makeMap(BASELINE)] },
]) {
  test(`${scenario.name} does not notify`, async ({ page }) => {
    await baseline(page)
    const state = await mockMaps(page, scenario.maps)
    await page.goto("/servers")
    await expect.poll(() => state.checks.length).toBeGreaterThan(0)
    await expect(mapsDot(page)).toHaveCount(0)
  })
}

test("direct catalog loads clear the baseline, detail visits do not", async ({
  page,
}) => {
  await baseline(page)
  await mockMaps(page, [makeMap("2026-10-20T10:00:00Z")])
  await page.goto("/maps/kz_notification_test/reviews")
  await expect(
    page.getByRole("link", { name: "Maps", exact: true }),
  ).toBeVisible()
  expect(
    await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY),
  ).toBe(BASELINE)
  await page.goto("/maps")
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY))
    .not.toBe(BASELINE)
  await page.goto("/servers")
  await expect(mapsDot(page)).toHaveCount(0)
})

test("catalog visits synchronize other tabs", async ({ page, context }) => {
  await baseline(page)
  await mockMaps(page, [makeMap("2026-10-20T10:00:00Z")])
  await page.goto("/servers")
  await expect(mapsDot(page)).toBeVisible()
  const otherTab = await context.newPage()
  await otherTab.goto("/maps")
  await expect
    .poll(() =>
      otherTab.evaluate((key) => localStorage.getItem(key), STORAGE_KEY),
    )
    .not.toBe(BASELINE)
  await expect(mapsDot(page)).toHaveCount(0)
})

test("request failures do not notify", async ({ page }) => {
  await baseline(page)
  const state = await mockMaps(page, [makeMap("2026-10-20T10:00:00Z")])
  state.fail = true
  await page.goto("/servers")
  await expect.poll(() => state.checks.length).toBeGreaterThan(0)
  await expect(mapsDot(page)).toHaveCount(0)
})

test("blocked storage retains the baseline across navigation", async ({
  page,
}) => {
  await page.addInitScript((storageKey) => {
    const originalGetItem = Storage.prototype.getItem
    const originalSetItem = Storage.prototype.setItem
    Storage.prototype.getItem = function (key) {
      if (key === storageKey) throw new Error("Storage blocked")
      return originalGetItem.call(this, key)
    }
    Storage.prototype.setItem = function (key, value) {
      if (key === storageKey) throw new Error("Storage blocked")
      return originalSetItem.call(this, key, value)
    }
  }, STORAGE_KEY)
  const state = await mockMaps(page, [makeMap(BASELINE)])
  await page.goto("/servers")
  await expect.poll(() => state.checks.length).toBeGreaterThan(0)
  await expect(mapsDot(page)).toHaveCount(0)
  state.maps = [makeMap(new Date(NOW + 30_000).toISOString())]
  await page.clock.fastForward(60_000)
  await expect(mapsDot(page)).toBeVisible()
  await page.getByRole("link", { name: "Maps", exact: true }).click()
  await expect(page).toHaveURL(/\/maps$/)
  await page.getByRole("link", { name: "Servers", exact: true }).click()
  await expect(mapsDot(page)).toHaveCount(0)
  await page.clock.fastForward(60_000)
  await expect(mapsDot(page)).toHaveCount(0)
})
