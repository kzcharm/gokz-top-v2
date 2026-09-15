import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const profileSteamid64 = "76561198000000001"
const otherSteamid64 = "76561198000000002"

const player = {
  name: "Live Runner",
  alias: null,
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64: profileSteamid64,
}

function buildRecord({
  mapId,
  mapName,
  uuid,
}: {
  mapId: number
  mapName: string
  uuid: string
}) {
  return {
    uuid,
    id: mapId,
    player: {
      steamid64: profileSteamid64,
      display_name: player.name,
    },
    steam_id: null,
    server_id: 100,
    server_name: "Live Records Server",
    server_group: null,
    map_id: mapId,
    map_name: mapName,
    workshop_id: null,
    map_tier: 4,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 42.123,
    teleports: 1,
    points: 350,
    raw_rating_contribution: 17,
    created_on: "2026-03-30T12:00:00Z",
    updated_on: "2026-03-30T12:00:00Z",
    updated_by: profileSteamid64,
    replay_id: null,
    is_replay_available: false,
    is_valid: true,
  }
}

const initialRecord = buildRecord({
  mapId: 1001,
  mapName: "kz_live_initial",
  uuid: "019d1111-1111-7111-8111-111111111111",
})
const liveRecord = buildRecord({
  mapId: 1002,
  mapName: "kz_live_arrival",
  uuid: "019d2222-2222-7222-8222-222222222222",
})

async function installWebSocketMock(page: Page) {
  await page.addInitScript(() => {
    const sockets: Array<{
      url: string
      closed: boolean
      onopen: ((event: Event) => void) | null
      onmessage: ((event: { data: string }) => void) | null
      onclose: ((event: Event) => void) | null
      onerror: ((event: Event) => void) | null
      dispatchMessage: (payload: unknown) => void
    }> = []

    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      readonly url: string
      closed = false
      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(url: string) {
        this.url = url
        sockets.push(this)
        queueMicrotask(() => {
          if (this.closed) {
            return
          }
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event("open"))
        })
      }

      send(_data?: unknown) {}

      close() {
        if (this.closed) {
          return
        }
        this.closed = true
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new Event("close"))
      }

      dispatchMessage(payload: unknown) {
        this.onmessage?.({ data: JSON.stringify(payload) })
      }
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      value: MockWebSocket,
    })

    Object.assign(window, {
      __recordSockets: sockets,
      __dispatchRecordMessage: (payload: unknown) => {
        for (const socket of sockets) {
          if (socket.url.includes("/v1/ws/records/recent") && !socket.closed) {
            socket.dispatchMessage(payload)
          }
        }
      },
    })
  })
}

async function installProfileRoutes({
  currentUserSteamid64,
  page,
  records,
}: {
  currentUserSteamid64: string | null
  page: Page
  records: () => Array<ReturnType<typeof buildRecord>>
}) {
  if (currentUserSteamid64) {
    await page.addInitScript((steamid64) => {
      const payload = btoa(JSON.stringify({ sub: steamid64 }))
      localStorage.setItem("access_token", `header.${payload}.signature`)
    }, currentUserSteamid64)
  }

  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname

    if (path === "/v1/users/me") {
      await route.fulfill({
        status: currentUserSteamid64 ? 200 : 401,
        contentType: "application/json",
        body: JSON.stringify(
          currentUserSteamid64
            ? { steamid64: currentUserSteamid64, roles: [], player: null }
            : { detail: "Unauthorized" },
        ),
      })
      return
    }
    if (path === "/v1/me/settings") {
      await route.fulfill({ json: {} })
      return
    }
    if (path === "/v1/me/hidden-maps") {
      await route.fulfill({ json: { data: [] } })
      return
    }
    if (path === "/v1/records/pb") {
      await route.fulfill({ json: records() })
      return
    }
    if (path === "/v1/maps/wrs") {
      await route.fulfill({ json: [] })
      return
    }
    if (path === "/v1/maps") {
      await route.fulfill({ json: [] })
      return
    }
    if (path === "/v1/bans") {
      await route.fulfill({ json: { data: [], count: 0 } })
      return
    }
    if (/^\/v1\/leaderboards\/players\/[^/]+$/.test(path)) {
      await route.fulfill({
        json: { rank: 1, rank_regional: 1, region: "EU", rating: 10 },
      })
      return
    }
    if (/^\/v1\/players\/[^/]+\/views$/.test(path)) {
      await route.fulfill({ json: { profile_views: 0 } })
      return
    }
    if (/^\/v1\/players\/[^/]+\/likes$/.test(path)) {
      await route.fulfill({ json: { player_likes: 0, created: false } })
      return
    }
    if (/^\/v1\/players\/[^/]+\/stats$/.test(path)) {
      await route.fulfill({
        json: {
          steamid64: profileSteamid64,
          daily_activity: null,
          playtime: { updated_at: null, total_seconds: 0 },
        },
      })
      return
    }
    if (/^\/v1\/players\/[^/]+\/follow-summary$/.test(path)) {
      await route.fulfill({
        json: {
          follower_count: 0,
          following_count: 0,
          viewer_is_following: null,
          viewer_is_self: currentUserSteamid64 === profileSteamid64,
        },
      })
      return
    }
    if (/^\/v1\/players\/[^/]+\/pinned-records$/.test(path)) {
      await route.fulfill({ json: { data: [] } })
      return
    }
    if (/^\/v1\/players\/[^/]+\/jumpstats$/.test(path)) {
      await route.fulfill({ json: { data: [], count: 0 } })
      return
    }
    if (/^\/v1\/players\/[^/]+$/.test(path)) {
      await route.fulfill({ json: player })
      return
    }

    await route.fulfill({ status: 404, json: { detail: "Not mocked" } })
  })
}

async function recentRecordSocketUrls(page: Page) {
  return await page.evaluate(() => {
    const state = window as typeof window & {
      __recordSockets: Array<{ url: string }>
    }
    return state.__recordSockets
      .map((socket) => socket.url)
      .filter((url) => url.includes("/v1/ws/records/recent"))
  })
}

test("own runs page subscribes to player-filtered live records", async ({
  page,
}) => {
  let includeLiveRecord = false
  await installWebSocketMock(page)
  await installProfileRoutes({
    currentUserSteamid64: profileSteamid64,
    page,
    records: () =>
      includeLiveRecord ? [initialRecord, liveRecord] : [initialRecord],
  })

  await page.goto(`/profile/${profileSteamid64}/runs`)
  await expect(page.getByText("kz_live_initial")).toBeVisible()
  await expect.poll(() => recentRecordSocketUrls(page)).toHaveLength(1)

  const socketUrl = new URL((await recentRecordSocketUrls(page))[0])
  expect(socketUrl.searchParams.get("scope")).toBe("OVR")
  expect(socketUrl.searchParams.get("steamid64")).toBe(profileSteamid64)

  includeLiveRecord = true
  await page.evaluate(
    ({ record, steamid64 }) => {
      const state = window as typeof window & {
        __dispatchRecordMessage: (payload: unknown) => void
      }
      state.__dispatchRecordMessage({
        type: "record.upserted",
        record: {
          uuid: record.uuid,
          player: { steamid64, display_name: "Live Runner" },
        },
      })
    },
    { record: liveRecord, steamid64: profileSteamid64 },
  )

  await expect(page.getByText("kz_live_arrival")).toBeVisible()

  await page.getByRole("button", { name: "Select record scope" }).click()
  await page.getByRole("menuitemradio", { name: "SKZ" }).click()
  await expect.poll(() => recentRecordSocketUrls(page)).toHaveLength(2)
  const scopeSocketState = await page.evaluate(() => {
    const state = window as typeof window & {
      __recordSockets: Array<{ url: string; closed: boolean }>
    }
    return state.__recordSockets.filter((socket) =>
      socket.url.includes("/v1/ws/records/recent"),
    )
  })
  expect(scopeSocketState[0].closed).toBe(true)
  expect(new URL(scopeSocketState[1].url).searchParams.get("scope")).toBe("SKZ")

  await page.goto("/maps")
  await expect
    .poll(async () => {
      return await page.evaluate(() => {
        const state = window as typeof window & {
          __recordSockets: Array<{ url: string; closed: boolean }>
        }
        return state.__recordSockets
          .filter((socket) => socket.url.includes("/v1/ws/records/recent"))
          .every((socket) => socket.closed)
      })
    })
    .toBe(true)
})

for (const visitor of [null, otherSteamid64]) {
  test(`${visitor ? "another player" : "an anonymous visitor"} does not subscribe to profile records`, async ({
    page,
  }) => {
    await installWebSocketMock(page)
    await installProfileRoutes({
      currentUserSteamid64: visitor,
      page,
      records: () => [initialRecord],
    })

    await page.goto(`/profile/${profileSteamid64}/runs`)
    await expect(page.getByText("kz_live_initial")).toBeVisible()
    await expect.poll(() => recentRecordSocketUrls(page)).toEqual([])
  })
}
