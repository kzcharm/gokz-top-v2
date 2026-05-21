import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

async function stubRegions(page: Page) {
  await page.route("**/v1/regions", async (route) => {
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
const currentUserSteamid64 = "76561198009999999"

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

function createLeaderboardRecord({
  index,
  steamid64,
  displayName,
  country,
  teleports,
  time,
  replayAvailable = false,
}: {
  index: number
  steamid64: string
  displayName: string
  country: string
  teleports: number
  time: number
  replayAvailable?: boolean
}) {
  return {
    country,
    record: {
      uuid: `019e${`${index}`.padStart(4, "0")}-${`${index}`.padStart(4, "0")}-7${`${index}`.padStart(3, "0")}-8${`${index}`.padStart(3, "0")}-${`${index}`.padStart(12, "0")}`,
      id: 980900 + index,
      player: {
        steamid64,
        display_name: displayName,
      },
      steam_id: null,
      server_id: 980300 + index,
      server_name: `Server ${index}`,
      map_id: seededMaps[0].id,
      map_name: seededMaps[0].name,
      map_tier: seededMaps[0].tiers.OVR,
      mode_id: teleports === 0 ? 200 : 201,
      mode: teleports === 0 ? "KZT" : "SKZ",
      stage: 0,
      tickrate: 128,
      time,
      teleports,
      points: 500 - index * 10,
      created_on: `2026-03-${`${(index % 28) + 1}`.padStart(2, "0")}T12:00:00Z`,
      updated_on: `2026-03-${`${(index % 28) + 1}`.padStart(2, "0")}T12:00:00Z`,
      updated_by: steamid64,
      replay_id: null,
      is_replay_available: replayAvailable,
      is_valid: true,
    },
  }
}

const mapLeaderboardSeedRows = [
  createLeaderboardRecord({
    index: 1,
    steamid64: "76561198000000001",
    displayName: "Alpha Runner",
    country: "DE",
    teleports: 0,
    time: 41.123,
    replayAvailable: true,
  }),
  createLeaderboardRecord({
    index: 2,
    steamid64: "76561198000000002",
    displayName: "Bravo Runner",
    country: "FR",
    teleports: 0,
    time: 42.456,
  }),
  createLeaderboardRecord({
    index: 3,
    steamid64: "76561198000000003",
    displayName: "Charlie Runner",
    country: "US",
    teleports: 0,
    time: 43.789,
  }),
  createLeaderboardRecord({
    index: 4,
    steamid64: "76561198000000004",
    displayName: "Delta Runner",
    country: "DE",
    teleports: 2,
    time: 44.111,
  }),
  createLeaderboardRecord({
    index: 5,
    steamid64: "76561198000000005",
    displayName: "Echo Runner",
    country: "FR",
    teleports: 0,
    time: 45.222,
  }),
  createLeaderboardRecord({
    index: 6,
    steamid64: "76561198000000006",
    displayName: "Foxtrot Runner",
    country: "US",
    teleports: 3,
    time: 46.333,
  }),
  createLeaderboardRecord({
    index: 7,
    steamid64: "76561198000000007",
    displayName: "Golf Runner",
    country: "DE",
    teleports: 0,
    time: 47.444,
  }),
  createLeaderboardRecord({
    index: 8,
    steamid64: "76561198000000008",
    displayName: "Hotel Runner",
    country: "FR",
    teleports: 2,
    time: 48.555,
  }),
  createLeaderboardRecord({
    index: 9,
    steamid64: "76561198000000009",
    displayName: "India Runner",
    country: "US",
    teleports: 0,
    time: 49.666,
  }),
  createLeaderboardRecord({
    index: 10,
    steamid64: "76561198000000010",
    displayName: "Juliet Runner",
    country: "DE",
    teleports: 1,
    time: 50.777,
  }),
  createLeaderboardRecord({
    index: 11,
    steamid64: currentUserSteamid64,
    displayName: "My Runner",
    country: "US",
    teleports: 2,
    time: 51.888,
  }),
  createLeaderboardRecord({
    index: 12,
    steamid64: "76561198000000012",
    displayName: "Kilo Runner",
    country: "FR",
    teleports: 4,
    time: 52.999,
  }),
]

test("Maps catalog supports search, sorting, pagination, and map detail navigation", async ({
  page,
}) => {
  let mapsRequestUrl = ""
  const leaderboardRequests: Array<{
    type: string | null
    limit: string | null
    offset: string | null
    scope: string | null
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

  await page.route(/\/v1\/maps\/\d+\/leaderboard(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    const scope = url.searchParams.get("scope")
    const type = url.searchParams.get("type")
    const country = url.searchParams.get("country")
    const region = url.searchParams.get("region")
    const offset = Number(url.searchParams.get("offset") ?? "0")
    const limit = Number(url.searchParams.get("limit") ?? "20")

    leaderboardRequests.push({
      scope,
      type,
      limit: url.searchParams.get("limit"),
      offset: url.searchParams.get("offset"),
      country,
      region,
    })

    if (scope === "SKZ") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [],
          count: 0,
          unique_nub_finishes: 0,
          unique_pro_finishes: 0,
          current_user_rank: null,
          current_user_steamid64: null,
        }),
      })
      return
    }

    const filteredRows = mapLeaderboardSeedRows.filter((row) => {
      if (type === "PRO" && row.record.teleports !== 0) {
        return false
      }
      if (country && row.country !== country) {
        return false
      }
      if (region === "EU" && !["DE", "FR"].includes(row.country)) {
        return false
      }
      return true
    })
    const currentUserRank =
      filteredRows.findIndex(
        (row) => row.record.player.steamid64 === currentUserSteamid64,
      ) + 1
    const proCount = mapLeaderboardSeedRows.filter((row) => {
      if (row.record.teleports !== 0) {
        return false
      }
      if (country && row.country !== country) {
        return false
      }
      if (region === "EU" && !["DE", "FR"].includes(row.country)) {
        return false
      }
      return true
    }).length
    const nubCount = mapLeaderboardSeedRows.filter((row) => {
      if (country && row.country !== country) {
        return false
      }
      if (region === "EU" && !["DE", "FR"].includes(row.country)) {
        return false
      }
      return true
    }).length

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: filteredRows
          .slice(offset, offset + limit)
          .map((row) => row.record),
        count: filteredRows.length,
        unique_nub_finishes: nubCount,
        unique_pro_finishes: proCount,
        current_user_rank: currentUserRank > 0 ? currentUserRank : null,
        current_user_steamid64: currentUserSteamid64,
      }),
    })
  })

  await page.goto("/maps")

  await expect(page).toHaveURL(/\/maps$/)
  await expect(page.getByTestId("map-card-kz_alpha")).toBeVisible()
  await expect(page.getByText("30 maps loaded")).toBeVisible()
  await expect(page.getByText("Page 1 of 2")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_alpha")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_omega")).toHaveCount(0)

  await page.keyboard.press("KeyS")
  await expect
    .poll(async () => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(0)

  await page.keyboard.press("KeyW")
  await expect.poll(async () => page.evaluate(() => window.scrollY)).toBe(0)

  await page.keyboard.press("KeyD")
  await expect(page.getByText("Page 2 of 2")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_omega")).toBeVisible()

  const searchBox = page.getByRole("textbox", { name: "Search maps by name" })
  await searchBox.focus()
  await page.keyboard.press("KeyA")
  await expect(searchBox).toHaveValue("a")
  await expect(page.getByText("Page 2 of 2")).toBeVisible()
  await searchBox.fill("")
  await page.getByText("30 maps loaded").click()

  await page.keyboard.press("KeyA")
  await expect(page.getByText("Page 1 of 2")).toBeVisible()

  expect(new URL(mapsRequestUrl).searchParams.get("is_validated")).toBe("true")
  expect(new URL(mapsRequestUrl).searchParams.get("scope")).toBeNull()
  expect(new URL(mapsRequestUrl).searchParams.get("difficulty")).toBeNull()

  await searchBox.fill("special")
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

  await page.reload()
  await expect(page.getByTestId("map-card-kz_alpha")).toBeVisible()
  await expect(page.locator('[data-testid="map-card-kz_alpha"] h2')).toHaveCSS(
    "user-select",
    "text",
  )
  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "OVR" }).click()
  await expect(
    page.getByRole("button", { name: "Select record scope" }),
  ).toContainText("OVR")
  await page.reload()
  await expect(page.getByTestId("map-card-kz_alpha")).toBeVisible()
  await page
    .getByTestId("map-card-kz_alpha")
    .getByRole("link", { name: "Open kz_alpha" })
    .click()

  await expect(page).toHaveURL(/\/maps\/kz_alpha$/)
  await expect(page.getByRole("heading", { name: "kz_alpha" })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Map Top" })).toBeVisible()
  await expect(page.getByText("Alpha Runner")).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Rank" })).toBeVisible()
  await expect(page.getByText("#1", { exact: true })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Player" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "Map" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Time" })).toHaveCount(0)
  await expect(
    page.locator("div").filter({ hasText: /^NUB$/ }).first(),
  ).toBeVisible()
  await expect(page.getByText(/11 \/ 12 91\.7%/)).toBeVisible()
  await expect(
    page.locator("div").filter({ hasText: /^PRO$/ }).first(),
  ).toBeVisible()
  await expect(page.getByText(/N\/A \/ 6/)).toBeVisible()

  await page
    .getByRole("button", { name: "Zoom map image for kz_alpha" })
    .click()
  await expect(
    page.getByRole("img", { name: "kz_alpha preview image enlarged" }),
  ).toBeVisible()
  await page.keyboard.press("Escape")

  await page.getByRole("combobox").last().click()
  await page.getByRole("option", { name: "10", exact: true }).click()
  await page.getByRole("button", { name: "Find Me" }).click()
  await expect
    .poll(() =>
      leaderboardRequests.some(
        (request) =>
          request.scope === "OVR" &&
          request.type === "NUB" &&
          request.limit === "10" &&
          request.offset === "10" &&
          request.country === null &&
          request.region === null,
      ),
    )
    .toBe(true)
  await expect(page.getByText("My Runner")).toBeVisible()

  await page.getByRole("switch", { name: "Pro only" }).click()
  await expect
    .poll(() =>
      leaderboardRequests.some(
        (request) =>
          request.scope === "OVR" &&
          request.type === "PRO" &&
          request.limit === "10" &&
          request.offset === "0" &&
          request.country === null &&
          request.region === null,
      ),
    )
    .toBe(true)
  await expect(page.getByText("Delta Runner")).toHaveCount(0)
  await expect(page.getByText(/N\/A \/ 6/)).toBeVisible()

  await page.getByRole("button", { name: /^(All countries|country)$/ }).click()
  await page.getByRole("button", { name: "Germany" }).click()
  await expect
    .poll(() =>
      leaderboardRequests.some(
        (request) =>
          request.scope === "OVR" &&
          request.type === "PRO" &&
          request.limit === "10" &&
          request.offset === "0" &&
          request.country === "DE" &&
          request.region === null,
      ),
    )
    .toBe(true)

  await page.getByRole("combobox").first().click()
  await page.getByRole("option", { name: /^EU$/ }).click()
  await expect
    .poll(() =>
      leaderboardRequests.some(
        (request) =>
          request.scope === "OVR" &&
          request.type === "PRO" &&
          request.limit === "10" &&
          request.offset === "0" &&
          request.country === null &&
          request.region === "EU",
      ),
    )
    .toBe(true)

  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ" }).click()
  await expect(
    page.getByText(
      "No stage 0 pro records found for this map in the selected scope.",
    ),
  ).toBeVisible()

  expect(leaderboardRequests).toEqual(
    expect.arrayContaining([
      {
        scope: "OVR",
        type: "NUB",
        limit: "20",
        offset: "0",
        country: null,
        region: null,
      },
      {
        scope: "OVR",
        type: "PRO",
        limit: "10",
        offset: "0",
        country: null,
        region: null,
      },
      {
        scope: "OVR",
        type: "PRO",
        limit: "10",
        offset: "0",
        country: "DE",
        region: null,
      },
      {
        scope: "OVR",
        type: "PRO",
        limit: "10",
        offset: "0",
        country: null,
        region: "EU",
      },
      {
        scope: "SKZ",
        type: "PRO",
        limit: "10",
        offset: "0",
        country: null,
        region: "EU",
      },
      {
        scope: "OVR",
        type: "NUB",
        limit: "10",
        offset: "10",
        country: null,
        region: null,
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

  await page.route(/\/v1\/maps\/\d+\/leaderboard(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    })
  })

  await page.goto(`/maps/${seededMaps[0].name}`)

  await expect(page.getByText("Unable to load map leaderboard")).toBeVisible()
})

test("Map detail opens the replay viewer for an available run replay", async ({
  page,
}) => {
  await page.addInitScript(() => {
    let lastOpenedUrl = ""
    Object.defineProperty(window, "__lastOpenedUrl", {
      configurable: true,
      get: () => lastOpenedUrl,
      set: (value: string) => {
        lastOpenedUrl = value
      },
    })
    Object.defineProperty(window, "open", {
      configurable: true,
      value: (url?: string | URL) => {
        lastOpenedUrl =
          typeof url === "string" ? url : url?.toString?.() ?? ""
        return null
      },
    })
  })
  await stubRegions(page)

  await page.route(/\/v1\/maps\/name\/[^/?]+(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seededMaps[0]),
    })
  })

  await page.route(/\/v1\/maps\/\d+\/leaderboard(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [mapLeaderboardSeedRows[0].record],
        count: 1,
        unique_nub_finishes: 1,
        unique_pro_finishes: 1,
        current_user_rank: null,
        current_user_steamid64: null,
      }),
    })
  })

  await page.goto(`/maps/${seededMaps[0].name}`)

  await expect(page.getByText("Alpha Runner")).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Play this run replay" }),
  ).toBeVisible()
  await page.getByRole("button", { name: "Play this run replay" }).click()
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as Window & { __lastOpenedUrl?: string }).__lastOpenedUrl ??
          "",
      ),
    )
    .toBe("http://localhost:5180/?replay=019e0001-0001-7001-8001-000000000001")
})
