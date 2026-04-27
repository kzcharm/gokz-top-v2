import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

async function stubRegions(page: Page) {
  await page.route("**/v1/regions/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 2,
        data: [
          { code: "EU", name: "Europe", country_codes: ["DE", "FR"] },
          { code: "AS", name: "Asia", country_codes: ["JP"] },
        ],
      }),
    })
  })
}

function createMap(index: number) {
  const paddedIndex = `${index}`.padStart(2, "0")
  const baseTier = (index % 8) + 1

  return {
    id: 980000 + index,
    name: `kz_map_${paddedIndex}`,
    filesize: 125000 + index,
    validated: index % 2 === 0,
    tiers: {
      OVR: baseTier,
      KZT: baseTier,
      SKZ: baseTier,
      VNL: baseTier,
    },
    created_on: `2026-03-${`${(index % 28) + 1}`.padStart(2, "0")}T08:00:00Z`,
    updated_on: `2026-03-${`${(index % 28) + 1}`.padStart(2, "0")}T12:00:00Z`,
    approved_by_steamid64: "76561198003275951",
    workshop_id: 1986459000 + index,
    synced_at: `2026-03-${`${(index % 28) + 1}`.padStart(2, "0")}T15:00:00Z`,
    authors: [],
    no_steamid_names: [],
    workshop_url: `https://steamcommunity.com/sharedfiles/filedetails/?id=${1986459000 + index}`,
  }
}

const seededMaps = Array.from({ length: 30 }, (_, index) =>
  createMap(index + 1),
)

seededMaps[0] = {
  ...seededMaps[0],
  name: "kz_alpha",
  tiers: {
    OVR: 2,
    KZT: 2,
    SKZ: 8,
    VNL: 4,
  },
  updated_on: "2026-03-01T12:00:00Z",
}

seededMaps[1] = {
  ...seededMaps[1],
  name: "kz_omega",
  tiers: {
    OVR: 8,
    KZT: 8,
    SKZ: 1,
    VNL: 2,
  },
  updated_on: "2026-03-30T12:00:00Z",
}

seededMaps[2] = {
  ...seededMaps[2],
  name: "kz_special_search",
  tiers: {
    OVR: 5,
    KZT: 5,
    SKZ: 5,
    VNL: 5,
  },
  updated_on: "2026-03-15T12:00:00Z",
}

const mapLeaderboardRecords = [
  {
    uuid: "019e1111-1111-7111-8111-111111111111",
    id: 980900,
    steamid64: "76561198000000001",
    player_name: "Alpha Runner",
    player_avatar_hash: null,
    steam_id: null,
    server_id: 980300,
    server_name: "Alpha Server",
    map_id: seededMaps[0].id,
    map_name: seededMaps[0].name,
    map_tier: seededMaps[0].tiers.OVR,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 41.123,
    teleports: 0,
    points: 415,
    created_on: "2026-03-31T12:00:00Z",
    updated_on: "2026-03-31T12:00:00Z",
    updated_by: "76561198000000001",
    replay_id: null,
    is_valid: true,
  },
  {
    uuid: "019e2222-2222-7222-8222-222222222222",
    id: 980901,
    steamid64: "76561198000000002",
    player_name: "TP Runner",
    player_avatar_hash: null,
    steam_id: null,
    server_id: 980301,
    server_name: "Teleport Server",
    map_id: seededMaps[0].id,
    map_name: seededMaps[0].name,
    map_tier: seededMaps[0].tiers.OVR,
    mode_id: 201,
    mode: "SKZ",
    stage: 0,
    tickrate: 128,
    time: 44.456,
    teleports: 3,
    points: 320,
    created_on: "2026-03-30T12:00:00Z",
    updated_on: "2026-03-30T12:00:00Z",
    updated_by: "76561198000000002",
    replay_id: null,
    is_valid: true,
  },
]

test("Maps catalog supports search, sorting, pagination, and map detail navigation", async ({
  page,
}) => {
  let mapsRequestUrl = ""
  const pbRequests: Array<{
    isProOnly: string | null
    limit: string | null
    mapId: string | null
    scope: string | null
    stage: string | null
    country: string | null
    region: string | null
  }> = []

  await page.addInitScript(() => {
    localStorage.setItem("gokz-datetime-format", "iso")
  })
  await stubRegions(page)

  await page.route(/\/v1\/maps(\?.*)?$/, async (route) => {
    mapsRequestUrl = route.request().url()
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seededMaps),
    })
  })

  await page.route(/\/v1\/maps\/name\/[^/?]+(\?.*)?$/, async (route) => {
    const name = decodeURIComponent(
      route.request().url().split("/name/")[1] ?? "",
    )
    const map = seededMaps.find((entry) => entry.name === name)

    if (!map) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Map not found" }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(map),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const isProOnly = url.searchParams.get("is_pro_only")
    const scope = url.searchParams.get("scope")
    const mapId = url.searchParams.get("map_id")

    pbRequests.push({
      scope,
      isProOnly,
      limit: url.searchParams.get("limit"),
      stage: url.searchParams.get("stage"),
      mapId,
      country: url.searchParams.get("country"),
      region: url.searchParams.get("region"),
    })

    const payload =
      scope === "SKZ"
        ? []
        : isProOnly === "true"
          ? [mapLeaderboardRecords[0]]
          : mapLeaderboardRecords

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    })
  })

  await page.goto("/maps")

  await expect(page).toHaveURL(/\/maps$/)
  await expect(page.getByTestId("map-card-kz_alpha")).toBeVisible()
  await expect(page.getByText("30 maps loaded")).toBeVisible()
  await expect(page.getByText("Page 1 of 2")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_alpha")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_omega")).toHaveCount(0)

  expect(new URL(mapsRequestUrl).searchParams.get("is_validated")).toBe("true")
  expect(new URL(mapsRequestUrl).searchParams.get("scope")).toBeNull()
  expect(new URL(mapsRequestUrl).searchParams.get("difficulty")).toBeNull()

  await page
    .getByRole("textbox", { name: "Search maps by name" })
    .fill("special")
  await expect(page.getByTestId("map-card-kz_special_search")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_alpha")).toHaveCount(0)

  await page.getByRole("textbox", { name: "Search maps by name" }).fill("")
  await page.getByRole("button", { name: "Updated" }).click()

  const firstCard = page.locator('[data-testid^="map-card-"]').first()
  await expect(firstCard).toHaveAttribute("data-testid", "map-card-kz_alpha")

  await page.getByRole("button", { name: "Go to page 2" }).click()
  await expect(page.getByText("Page 2 of 2")).toBeVisible()

  await page.getByRole("button", { name: "Go to page 1" }).click()

  await page.getByRole("button", { name: "Tier" }).click()
  await expect(firstCard).toHaveAttribute("data-testid", "map-card-kz_map_08")

  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ" }).click()

  await page.evaluate(() => {
    localStorage.setItem("gokz-app-scope", "OVR")
  })
  await page.reload()
  await expect(page.getByTestId("map-card-kz_alpha")).toBeVisible()
  await expect(page.locator('[data-testid="map-card-kz_alpha"] h2')).toHaveCSS(
    "user-select",
    "text",
  )

  await page
    .getByTestId("map-card-kz_alpha")
    .getByRole("link", { name: "Open kz_alpha" })
    .click()

  await expect(page).toHaveURL(/\/maps\/kz_alpha$/)
  await expect(page.getByRole("heading", { name: "kz_alpha" })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Map Top" })).toBeVisible()
  await expect(page.getByText("Alpha Runner")).toBeVisible()
  await expect(page.getByText("TP Runner")).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Rank" })).toBeVisible()
  await expect(page.getByText("#1")).toBeVisible()
  await expect(page.getByText("#2")).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Player" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Map" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Time" })).toHaveCount(0)

  await page.getByRole("switch", { name: "Pro only" }).click()
  await expect(page.getByText("Alpha Runner")).toBeVisible()
  await expect(page.getByText("TP Runner")).toHaveCount(0)

  await page.getByRole("button", { name: "All countries" }).click()
  await page.getByRole("button", { name: "Germany" }).click()
  await expect
    .poll(() => pbRequests.at(-1))
    .toMatchObject({
      mapId: `${seededMaps[0].id}`,
      scope: "OVR",
      isProOnly: "true",
      country: "DE",
      region: null,
    })

  await page.getByRole("combobox").filter({ hasText: "All regions" }).click()
  await page.getByRole("option", { name: /^EU$/ }).click()
  await expect
    .poll(() => pbRequests.at(-1))
    .toMatchObject({
      mapId: `${seededMaps[0].id}`,
      scope: "OVR",
      isProOnly: "true",
      country: null,
      region: "EU",
    })

  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ" }).click()
  await expect(
    page.getByText(
      "No stage 0 pro records found for this map in the selected scope.",
    ),
  ).toBeVisible()

  expect(pbRequests).toEqual(
    expect.arrayContaining([
      {
        scope: "OVR",
        isProOnly: "false",
        limit: "100",
        stage: "0",
        mapId: `${seededMaps[0].id}`,
        country: null,
        region: null,
      },
      {
        scope: "OVR",
        isProOnly: "true",
        limit: "100",
        stage: "0",
        mapId: `${seededMaps[0].id}`,
        country: null,
        region: null,
      },
      {
        scope: "OVR",
        isProOnly: "true",
        limit: "100",
        stage: "0",
        mapId: `${seededMaps[0].id}`,
        country: "DE",
        region: null,
      },
      {
        scope: "OVR",
        isProOnly: "true",
        limit: "100",
        stage: "0",
        mapId: `${seededMaps[0].id}`,
        country: null,
        region: "EU",
      },
      {
        scope: "SKZ",
        isProOnly: "true",
        limit: "100",
        stage: "0",
        mapId: `${seededMaps[0].id}`,
        country: null,
        region: "EU",
      },
    ]),
  )
})

test("Map detail shows not found for an unknown map", async ({ page }) => {
  await stubRegions(page)
  await page.route(/\/v1\/maps\/name\/[^/?]+(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Map not found" }),
    })
  })

  await page.goto("/maps/kz_missing_map")

  await expect(page.getByTestId("not-found")).toBeVisible()
})

test("Map detail shows leaderboard error state when PB loading fails", async ({
  page,
}) => {
  await stubRegions(page)
  await page.route(/\/v1\/maps\/name\/[^/?]+(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seededMaps[0]),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    })
  })

  await page.goto(`/maps/${seededMaps[0].name}`)

  await expect(page.getByText("Unable to load map leaderboard")).toBeVisible()
})
