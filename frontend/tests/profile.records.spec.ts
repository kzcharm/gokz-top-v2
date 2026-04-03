import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const appUrl = "http://127.0.0.1:4583"
const steamid64 = "76561198000000001"

const seededPlayer = {
  name: "Seed Runner",
  alias: "Seed Alias",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64,
}

const ovrRecords = [
  {
    uuid: "019d7777-7777-7777-8777-777777777777",
    id: 981100,
    steamid64,
    player_name: "Seed Runner",
    player_avatar_hash: null,
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980200,
    map_name: "kz_seed_alpha",
    map_tier: 4,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 42.123,
    teleports: 0,
    points: 350,
    created_on: "2026-03-30T12:00:00Z",
    updated_on: "2026-03-30T12:00:00Z",
    updated_by: steamid64,
    replay_id: 123,
    is_valid: true,
  },
  {
    uuid: "019d8888-8888-7888-8888-888888888888",
    id: 981101,
    steamid64,
    player_name: "Seed Runner",
    player_avatar_hash: null,
    steam_id: null,
    server_id: 980301,
    server_name: "Second Server",
    map_id: 980201,
    map_name: "kz_seed_beta",
    map_tier: 6,
    mode_id: 201,
    mode: "SKZ",
    stage: 0,
    tickrate: 128,
    time: 50.456,
    teleports: 3,
    points: 510,
    created_on: "2026-03-31T12:00:00Z",
    updated_on: "2026-03-31T12:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
]

test("Profile records page renders sidebar, filters, and scope-aware PB rows", async ({
  page,
}) => {
  const pbRequests: Array<{
    isProOnly: string | null
    scope: string | null
    stage: string | null
    steamid64: string | null
  }> = []

  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const scope = url.searchParams.get("scope")
    const isProOnly = url.searchParams.get("is_pro_only")

    pbRequests.push({
      scope,
      isProOnly,
      stage: url.searchParams.get("stage"),
      steamid64: url.searchParams.get("steamid64"),
    })

    const payload =
      scope === "SKZ" ? [] : isProOnly === "true" ? [ovrRecords[0]] : ovrRecords

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    })
  })

  await page.goto(`${appUrl}/profile/${steamid64}/records`)

  await expect(
    page.getByRole("heading", { name: "Stage 0 records for Seed Alias" }),
  ).toBeVisible()
  await expect(page.getByRole("heading", { name: "Seed Alias" })).toBeVisible()
  await expect(page.getByText("Skill radar")).toBeVisible()

  await expect(page.getByRole("columnheader", { name: "Map" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Mode" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Tier" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "TPs" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Time" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Points" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Server" })).toBeVisible()
  await expect(
    page.getByRole("columnheader", { name: "Datetime" }),
  ).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Player" })).toHaveCount(
    0,
  )

  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.getByText("kz_seed_beta")).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(2)

  await page.getByRole("switch", { name: "Pro only" }).click()

  await expect(page.getByText("kz_seed_alpha")).toBeVisible()
  await expect(page.getByText("kz_seed_beta")).toHaveCount(0)
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(1)

  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ" }).click()

  await expect(
    page.getByText(
      "No stage 0 pro records found for this player in the selected scope.",
    ),
  ).toBeVisible()
  await expect(page.locator('[data-testid^="pb-record-row-"]')).toHaveCount(0)

  expect(pbRequests).toEqual(
    expect.arrayContaining([
      {
        scope: "OVR",
        isProOnly: "false",
        stage: "0",
        steamid64,
      },
      {
        scope: "OVR",
        isProOnly: "true",
        stage: "0",
        steamid64,
      },
      {
        scope: "SKZ",
        isProOnly: "true",
        stage: "0",
        steamid64,
      },
    ]),
  )
})

test("Profile records page shows an error state when PB loading fails", async ({
  page,
}) => {
  await page.route(/\/v1\/players\/$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [seededPlayer],
      }),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    })
  })

  await page.goto(`${appUrl}/profile/${steamid64}/records`)

  await expect(
    page.getByText(
      "Failed to load profile records. Reload the page and try again.",
    ),
  ).toBeVisible()
})
