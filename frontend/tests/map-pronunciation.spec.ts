import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const maps = ["kz_21loop_final_fix", "bkz_hellokitty_v2"].map(
  (name, index) => ({
    id: 991700 + index,
    name,
    filesize: 100,
    validated: true,
    tiers: { OVR: 3, KZT: 3, SKZ: 3, VNL: 3 },
    created_on: "2026-01-01T00:00:00Z",
    updated_on: "2026-01-01T00:00:00Z",
    synced_at: "2026-01-01T00:00:00Z",
    approved_by_steamid64: "76561198000000001",
    workshop_id: null,
    authors: [],
    no_steamid_names: [],
    bonus_count: 0,
    review_summary: null,
  }),
)

const player = {
  steamid64: "76561198991700001",
  name: "★ Alpha_123 😊",
  alias: "Alpha",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_played_at: null,
}

async function setup(
  page: Page,
  {
    blocked = false,
    roles = null,
  }: { blocked?: boolean; roles?: string[] | null } = {},
) {
  await page.addInitScript(
    ({ blocked, roles }) => {
      localStorage.setItem("gokz-language", "en")
      if (roles !== null) localStorage.setItem("access_token", "mock-token")
      const calls: string[] = []
      Object.assign(window, { pronunciationCalls: calls })
      let rejectNext = blocked
      class MockAudio extends EventTarget {
        constructor(public src: string) {
          super()
        }
        play() {
          calls.push(`play:${this.src}`)
          if (rejectNext) {
            rejectNext = false
            return Promise.reject(
              new DOMException("Gesture required", "NotAllowedError"),
            )
          }
          return Promise.resolve()
        }
        pause() {
          calls.push(`pause:${this.src}`)
        }
      }
      Object.assign(window, { Audio: MockAudio })
    },
    { blocked, roles },
  )
  await page.routeWebSocket(/\/v1\/ws\//, () => {})
  const requests: string[] = []
  const corrections = new Map<
    string,
    { text: string; voice_id: string; language_code: string | null }
  >()
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path === "/v1/admin/pronunciations/options") {
      requests.push(`GET:${path}`)
      return route.fulfill({
        json: {
          voices: [
            { id: "DODLEQrClDo8wCz460ld", name: "Lauren" },
            { id: "jessica", name: "Jessica" },
          ],
          languages: [
            { code: "en", name: "English" },
            { code: "ja", name: "Japanese" },
          ],
          default_voice_id: "DODLEQrClDo8wCz460ld",
        },
      })
    }
    if (path.startsWith("/v1/admin/") && path.includes("/pronunciation")) {
      requests.push(`${route.request().method()}:${path}`)
      const base = path.replace("/admin", "").replace("/regenerate", "")
      if (route.request().method() === "POST")
        corrections.set(base, route.request().postDataJSON())
      const correction = corrections.get(base)
      const source = path.includes("/players/") ? "Alpha" : "21loop final"
      return route.fulfill({
        status: route.request().method() === "POST" ? 202 : 200,
        json: {
          status: "pending",
          spoken_text: correction?.text ?? source,
          source_text: source,
          voice_id: correction?.voice_id ?? "DODLEQrClDo8wCz460ld",
          language_code: correction?.language_code ?? null,
          audio_url: null,
        },
      })
    }
    if (path.endsWith("/pronunciation")) {
      requests.push(`${route.request().method()}:${path}`)
      return route.fulfill({
        json: {
          status: "ready",
          spoken_text: "21loop final",
          audio_url: `https://audio.example.test/${path.split("/")[3]}.mp3`,
        },
      })
    }
    if (path === "/v1/users/me" && roles !== null)
      return route.fulfill({
        json: {
          steamid64: "76561198991700002",
          roles,
          is_active: true,
          player,
        },
      })
    if (path === "/v1/users/me")
      return route.fulfill({
        status: 401,
        json: { detail: "Not authenticated" },
      })
    if (path === `/v1/players/${player.steamid64}`)
      return route.fulfill({ json: player })
    if (path.endsWith("/stats"))
      return route.fulfill({
        json: {
          steamid64: player.steamid64,
          daily_activity: null,
          playtime: { updated_at: null, total_seconds: 0 },
        },
      })
    if (path.startsWith("/v1/leaderboards/players/"))
      return route.fulfill({
        json: {
          rank: null,
          rank_regional: null,
          rating: null,
          points: 0,
          scope: "OVR",
          player: { steamid64: player.steamid64, display_name: "Alpha" },
        },
      })
    if (path.endsWith("/views"))
      return route.fulfill({ json: { profile_views: 0 } })
    if (path.endsWith("/likes"))
      return route.fulfill({ json: { player_likes: 0, viewer_likes_today: 0 } })
    if (path.endsWith("/setup"))
      return route.fulfill({
        json: { hardware: [], game_settings: {}, operating_system: null },
      })
    if (path === "/v1/maps")
      return route.fulfill({
        json: url.searchParams.has("name")
          ? maps.filter((map) => map.name === url.searchParams.get("name"))
          : maps,
      })
    if (path === "/v1/graphql") {
      const body = route.request().postDataJSON()
      return route.fulfill({
        json: {
          data: body.query.includes("MapImages")
            ? {
                mapImages: (body.variables.inputs ?? []).map(
                  (input: object) => ({ ...input, previewUrl: null }),
                ),
              }
            : { players: [] },
        },
      })
    }
    if (path === "/v1/leaderboards/maps")
      return route.fulfill({
        json: {
          count: maps.length,
          data: maps.map((map) => ({
            map: { id: map.id, name: map.name },
            total_playtime: 1000,
            average_playtime_per_player: 100,
            unique_nub_finishes: 10,
            unique_pro_finishes: 5,
            pro_nub_ratio: 0.5,
            total_finishes: 20,
            median_first_completion_time: 20,
          })),
        },
      })
    if (path.endsWith("/leaderboard"))
      return route.fulfill({
        json: {
          data: [],
          count: 0,
          unique_nub_finishes: 0,
          unique_pro_finishes: 0,
        },
      })
    if (path === "/v1/regions" || path === "/v1/me/settings")
      return route.fulfill({ json: {} })
    if (path === "/v1/maps/wrs" || path === "/v1/records/pb")
      return route.fulfill({ json: [] })
    return route.fulfill({ json: { data: [], count: 0, unread_count: 0 } })
  })
  return requests
}

async function audioCalls(page: Page) {
  return page.evaluate(
    () =>
      (window as unknown as { pronunciationCalls: string[] })
        .pronunciationCalls,
  )
}

test("anonymous map title playback is lazy and keyboard accessible", async ({
  page,
}) => {
  const requests = await setup(page)
  await page.goto(`/maps/${maps[0].name}/maptop`)
  const button = page.getByRole("button", {
    name: "Play pronunciation",
    exact: true,
  })
  await expect(button).toBeVisible()
  await expect(
    page.locator('[data-slot="badge"]').filter({ hasText: "T3" }).first(),
  ).toHaveCSS("box-shadow", "none")
  expect(requests).toEqual([])
  await button.focus()
  await page.keyboard.press("Enter")
  await expect(button).toHaveAttribute("aria-pressed", "true")
  expect(requests).toEqual(["POST:/v1/maps/991700/pronunciation"])
  expect(await audioCalls(page)).toEqual([
    "play:https://audio.example.test/991700.mp3",
  ])
  await page.screenshot({
    path: "../.temp/screenshots/map-pronunciation-title.png",
    fullPage: true,
  })
})

test("catalog name menu plays audio and switches without overlap", async ({
  page,
}) => {
  const requests = await setup(page)
  await page.goto("/maps")
  const first = page.getByTestId(`map-card-${maps[0].name}`)
  await expect(first).toBeVisible()
  expect(requests).toEqual([])
  await first
    .getByRole("link", { name: maps[0].name, exact: true })
    .click({ button: "right" })
  await expect(page.getByRole("menuitem")).toHaveText([
    "Copy Name",
    "Goto Page",
    "Download",
    "Play pronunciation",
  ])
  await expect(
    page.getByRole("group", { name: "Admin actions", exact: true }),
  ).toHaveCount(0)
  await page.getByRole("menuitem", { name: "Play pronunciation" }).click()
  await expect.poll(async () => (await audioCalls(page)).length).toBe(1)
  await expect(
    page.getByRole("menuitem", { name: "Play pronunciation" }),
  ).toHaveCount(0)
  await page
    .getByTestId(`map-card-${maps[1].name}`)
    .getByRole("link", { name: maps[1].name, exact: true })
    .click({ button: "right" })
  await page.getByRole("menuitem", { name: "Play pronunciation" }).click()
  await expect.poll(async () => (await audioCalls(page)).length).toBe(3)
  expect(await audioCalls(page)).toEqual([
    "play:https://audio.example.test/991700.mp3",
    "pause:https://audio.example.test/991700.mp3",
    "play:https://audio.example.test/991701.mp3",
  ])
})

test("MapDisplay menu resolves a name and plays pronunciation", async ({
  page,
}) => {
  const requests = await setup(page)
  await page.goto("/leaderboards/maps")
  const link = page
    .getByRole("link", { name: maps[0].name, exact: true })
    .first()
  await expect(link).toBeVisible()
  expect(requests).toEqual([])
  await link.click({ button: "right" })
  await expect(page.getByRole("menuitem")).toHaveText([
    "Copy Name",
    "Goto Page",
    "Download",
    "Play pronunciation",
  ])
  await expect(
    page.getByRole("group", { name: "Admin actions", exact: true }),
  ).toHaveCount(0)
  await page.getByRole("menuitem", { name: "Play pronunciation" }).click()
  await expect.poll(() => requests.length).toBe(1)
  await expect.poll(async () => (await audioCalls(page)).length).toBe(1)
})

test("pending generation polls until ready", async ({ page }) => {
  await setup(page)
  let polls = 0
  await page.route("**/v1/maps/991700/pronunciation", async (route) => {
    const ready = route.request().method() === "GET" && ++polls >= 2
    return route.fulfill({
      status: ready ? 200 : 202,
      json: {
        status: ready ? "ready" : "pending",
        spoken_text: "21loop final",
        audio_url: ready ? "https://audio.example.test/ready.mp3" : null,
      },
    })
  })
  await page.goto(`/maps/${maps[0].name}/maptop`)
  await page
    .getByRole("button", { name: "Play pronunciation", exact: true })
    .click()
  await expect(
    page.getByRole("button", { name: "Preparing pronunciation…", exact: true }),
  ).toBeDisabled()
  await expect.poll(async () => (await audioCalls(page)).length).toBe(1)
  expect(polls).toBe(2)
})

test("blocked playback retries within a user gesture without generating again", async ({
  page,
}) => {
  const requests = await setup(page, { blocked: true })
  await page.goto(`/maps/${maps[0].name}/maptop`)
  await page
    .getByRole("button", { name: "Play pronunciation", exact: true })
    .click()
  await expect(
    page.getByText(
      "Your browser paused audio playback. Select Play to listen.",
    ),
  ).toBeVisible()
  await page.getByRole("button", { name: "Play", exact: true }).click()
  await expect(
    page.getByRole("button", { name: "Play pronunciation", exact: true }),
  ).toHaveAttribute("aria-pressed", "true")
  expect(requests).toHaveLength(1)
  expect(await audioCalls(page)).toHaveLength(2)
})

test("generation failure gives a readable error", async ({ page }) => {
  await setup(page)
  await page.route("**/v1/maps/991700/pronunciation", (route) =>
    route.fulfill({ status: 503, json: { detail: "unavailable" } }),
  )
  await page.goto(`/maps/${maps[0].name}/maptop`)
  await page
    .getByRole("button", { name: "Play pronunciation", exact: true })
    .click()
  await expect(
    page.getByText("Could not play the pronunciation. Please try again later."),
  ).toBeVisible()
  expect(await audioCalls(page)).toEqual([])
})

test("a superseded generation request never plays its audio", async ({
  page,
}) => {
  await setup(page)
  let firstRequested = false
  let releaseFirst: (() => void) | undefined
  const waitForRelease = new Promise<void>((resolve) => {
    releaseFirst = resolve
  })
  await page.route("**/v1/maps/991700/pronunciation", async (route) => {
    firstRequested = true
    await waitForRelease
    await route.fulfill({
      json: {
        status: "ready",
        spoken_text: "21loop final",
        audio_url: "https://audio.example.test/stale.mp3",
      },
    })
  })
  await page.goto("/maps")
  await page
    .getByTestId(`map-card-${maps[0].name}`)
    .getByRole("link", { name: maps[0].name, exact: true })
    .click({ button: "right" })
  await page.getByRole("menuitem", { name: "Play pronunciation" }).click()
  await expect.poll(() => firstRequested).toBe(true)
  await expect(
    page.getByRole("menuitem", { name: "Preparing pronunciation…" }),
  ).toHaveCount(0)
  await page
    .getByTestId(`map-card-${maps[1].name}`)
    .getByRole("link", { name: maps[1].name, exact: true })
    .click({ button: "right" })
  await page.getByRole("menuitem", { name: "Play pronunciation" }).click()
  await expect.poll(async () => (await audioCalls(page)).length).toBe(1)
  releaseFirst?.()
  await expect(
    page
      .getByTestId(`map-card-${maps[0].name}`)
      .getByRole("link", { name: maps[0].name, exact: true }),
  ).toBeVisible()
  expect(await audioCalls(page)).toEqual([
    "play:https://audio.example.test/991701.mp3",
  ])
})

test("player profile pronunciation is public and lazy", async ({ page }) => {
  const requests = await setup(page)
  await page.goto(`/profile/${player.steamid64}`)
  await expect(page.getByTestId("profile-identity-surface")).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Play pronunciation", exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole("button", { name: "Regenerate pronunciation", exact: true }),
  ).toHaveCount(0)
  expect(requests).toEqual([])
  await page.getByTestId("profile-identity-surface").click({ button: "right" })
  const items = await page.getByRole("menuitem").allTextContents()
  expect(items.indexOf("Play pronunciation")).toBe(
    items.indexOf("Copy Name") + 1,
  )
  await page
    .getByRole("menuitem", { name: "Play pronunciation", exact: true })
    .click()
  await expect.poll(async () => (await audioCalls(page)).length).toBe(1)
  expect(requests).toEqual([
    `POST:/v1/players/${player.steamid64}/pronunciation`,
  ])
})

for (const kind of ["map", "player"] as const) {
  test(`admin regenerates ${kind} audio with voice, language and custom text`, async ({
    page,
  }) => {
    const requests = await setup(page, { roles: ["admin"] })
    await page.goto(
      kind === "map"
        ? `/maps/${maps[0].name}/maptop`
        : `/profile/${player.steamid64}`,
    )
    const openRegeneration = async () => {
      if (kind === "player") {
        await page
          .getByTestId("profile-identity-surface")
          .click({ button: "right" })
        const items = await page.getByRole("menuitem").allTextContents()
        expect(items.indexOf("Play pronunciation")).toBe(
          items.indexOf("Copy Name") + 1,
        )
        await expect(
          page
            .getByRole("group", { name: "Admin actions", exact: true })
            .getByRole("menuitem", {
              name: "Regenerate pronunciation",
              exact: true,
            }),
        ).toBeVisible()
        await page
          .getByRole("menuitem", {
            name: "Regenerate pronunciation",
            exact: true,
          })
          .click()
      } else {
        await expect(
          page.getByRole("button", {
            name: "Regenerate pronunciation",
            exact: true,
          }),
        ).toHaveCount(0)
        await page
          .getByRole("heading", { name: maps[0].name, exact: true })
          .click({ button: "right" })
        await expect(page.getByRole("menuitem")).toHaveText([
          "Copy Name",
          "Goto Page",
          "Download",
          "Play pronunciation",
          "Add Review",
          "Regenerate pronunciation",
        ])
        await page
          .getByRole("group", { name: "Admin actions", exact: true })
          .getByRole("menuitem", {
            name: "Regenerate pronunciation",
            exact: true,
          })
          .click()
      }
    }
    await openRegeneration()
    const dialog = page.getByRole("dialog", {
      name: "Regenerate pronunciation",
    })
    await expect(dialog.getByLabel("Text to speak")).toHaveValue(
      kind === "map" ? "21loop final" : "Alpha",
    )
    await expect(
      dialog.getByRole("combobox", { name: "Voice", exact: true }),
    ).toContainText("Lauren")
    await expect(dialog.getByText("Model", { exact: true })).toHaveCount(0)
    await dialog.getByRole("combobox", { name: "Voice", exact: true }).click()
    await page.getByRole("option", { name: "Jessica", exact: true }).click()
    await dialog
      .getByRole("combobox", { name: "Language", exact: true })
      .click()
    await page.getByRole("option", { name: "Japanese", exact: true }).click()
    await dialog.getByLabel("Text to speak").fill("Ah lou ette")
    if (kind === "map")
      await page.screenshot({
        path: "../.temp/screenshots/pronunciation-admin-dialog.png",
      })
    const request = page.waitForRequest(
      (item) =>
        item.method() === "POST" &&
        item.url().endsWith("/pronunciation/regenerate"),
    )
    await dialog.getByRole("button", { name: "Generate and play" }).click()
    expect((await request).postDataJSON()).toEqual({
      text: "Ah lou ette",
      voice_id: "jessica",
      language_code: "ja",
    })
    await expect(dialog).not.toBeVisible()
    await expect.poll(async () => (await audioCalls(page)).length).toBe(1)
    const prefix =
      kind === "map"
        ? `/v1/admin/maps/${maps[0].id}`
        : `/v1/admin/players/${player.steamid64}`
    expect(requests).toContain(`POST:${prefix}/pronunciation/regenerate`)
    // Reopening loads the saved correction; default controls restore the source.
    await openRegeneration()
    await expect(dialog.getByLabel("Text to speak")).toHaveValue("Ah lou ette")
    await dialog.getByRole("button", { name: "Use defaults" }).click()
    await expect(dialog.getByLabel("Text to speak")).toHaveValue(
      kind === "map" ? "21loop final" : "Alpha",
    )
    await expect(
      dialog.getByRole("combobox", { name: "Voice", exact: true }),
    ).toContainText("Lauren")
    await expect(
      dialog.getByRole("combobox", { name: "Language", exact: true }),
    ).toContainText("Automatic")
  })
}

test("map admin can regenerate from the catalog context menu", async ({
  page,
}) => {
  await setup(page, { roles: ["map_admin"] })
  await page.goto("/maps")
  await page
    .getByTestId(`map-card-${maps[0].name}`)
    .getByRole("link", { name: maps[0].name, exact: true })
    .click({ button: "right" })
  await page
    .getByRole("menuitem", { name: "Regenerate pronunciation", exact: true })
    .click()
  const dialog = page.getByRole("dialog", { name: "Regenerate pronunciation" })
  await expect(dialog.getByLabel("Text to speak")).toHaveValue("21loop final")
  await dialog.getByLabel("Text to speak").fill("A corrected name")
  await dialog.getByRole("button", { name: "Generate and play" }).click()
  await expect(dialog).not.toBeVisible()
  await expect.poll(async () => (await audioCalls(page)).length).toBe(1)
})

test("map admins cannot regenerate player names", async ({ page }) => {
  await setup(page, { roles: ["map_admin"] })
  await page.goto(`/profile/${player.steamid64}`)
  await expect(
    page.getByRole("button", { name: "Play pronunciation", exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole("button", { name: "Regenerate pronunciation", exact: true }),
  ).toHaveCount(0)
  await page.getByTestId("profile-identity-surface").click({ button: "right" })
  await expect(
    page.getByRole("menuitem", { name: "Play pronunciation", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", {
      name: "Regenerate pronunciation",
      exact: true,
    }),
  ).toHaveCount(0)
})

test("player playback stops map playback", async ({ page }) => {
  await setup(page)
  await page.goto(`/maps/${maps[0].name}/maptop`)
  await page
    .getByRole("button", { name: "Play pronunciation", exact: true })
    .click()
  await expect.poll(async () => (await audioCalls(page)).length).toBe(1)
  // Use client-side navigation to preserve the shared audio controller.
  await page.evaluate(() => {
    history.pushState(null, "", "/profile/76561198991700001")
    window.dispatchEvent(new PopStateEvent("popstate"))
  })
  await expect(page.getByTestId("profile-identity-surface")).toBeVisible()
  await page.getByTestId("profile-identity-surface").click({ button: "right" })
  await page
    .getByRole("menuitem", { name: "Play pronunciation", exact: true })
    .click()
  await expect.poll(async () => (await audioCalls(page)).length).toBe(3)
  expect(await audioCalls(page)).toEqual([
    "play:https://audio.example.test/991700.mp3",
    "pause:https://audio.example.test/991700.mp3",
    `play:https://audio.example.test/${player.steamid64}.mp3`,
  ])
})

test("admin settings errors can be retried without losing the page", async ({
  page,
}) => {
  await setup(page, { roles: ["admin"] })
  let fails = true
  await page.route("**/v1/admin/pronunciations/options", (route) =>
    fails
      ? route.fulfill({ status: 503, json: { detail: "unavailable" } })
      : route.fallback(),
  )
  await page.goto(`/maps/${maps[0].name}/maptop`)
  await page
    .getByRole("heading", { name: maps[0].name, exact: true })
    .click({ button: "right" })
  await page
    .getByRole("menuitem", { name: "Regenerate pronunciation", exact: true })
    .click()
  const dialog = page.getByRole("dialog", { name: "Regenerate pronunciation" })
  await expect(dialog.getByRole("alert")).toHaveText(
    "Could not load pronunciation settings. Please try again.",
  )
  fails = false
  await dialog.getByRole("button", { name: "Retry", exact: true }).click()
  await expect(dialog.getByLabel("Text to speak")).toHaveValue("21loop final")
})
