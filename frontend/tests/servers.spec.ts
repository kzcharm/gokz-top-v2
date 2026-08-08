import { readFile } from "node:fs/promises"
import type { Page } from "@playwright/test"
import { expect, test } from "@playwright/test"
import { randomSteamid64 } from "./utils/random"
import { logInUser } from "./utils/user"

test.use({ storageState: { cookies: [], origins: [] } })

const seedServers = {
  count: 1,
  data: [
    {
      id: "019d1111-1111-7111-8111-111111111111",
      ip: "10.0.0.1",
      port: 27015,
      region: "NA",
      status: "enabled",
      configured_hostname: "Alpha Seed",
      country: "US",
      city: "Chicago",
      source: "manual",
      last_discovered_at: null,
      map_tier: 2,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group: { id: "019d0000-0000-7000-8000-000000000001", name: "Seed Group" },
      live_status: {
        hostname: "Alpha Seed",
        map: "kz_seed",
        workshop_id: "123456789",
        player_count: 5,
        max_players: 16,
        players: [],
        is_online: true,
        updated_at: "2026-03-12T10:00:00Z",
        state: {
          last_plugin_seen_at: "2026-03-12T10:00:00Z",
          last_a2s_seen_at: "2026-03-12T10:00:00Z",
          last_successful_seen_at: "2026-03-12T10:00:00Z",
        },
        global_status: {
          api_key_valid: true,
          plugins_valid: true,
          settings_enforcer_valid: true,
          map_valid: true,
          modes: { KZT: true, SKZ: false, VNL: false },
          checked_at: "2026-03-12T10:00:00Z",
          eligible: true,
        },
      },
    },
  ],
}

const snapshotServers = {
  type: "server.snapshot",
  servers: [
    ...seedServers.data,
    {
      id: "019d2222-2222-7222-8222-222222222222",
      ip: "10.0.0.2",
      port: 27016,
      region: "EU",
      status: "enabled",
      configured_hostname: "Bravo Offline",
      country: "DE",
      city: "Berlin",
      source: "manual",
      last_discovered_at: null,
      map_tier: 7,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group: {
        id: "019d0000-0000-7000-8000-000000000002",
        name: "Berlin Group",
      },
      live_status: {
        hostname: "Bravo Offline",
        map: "kz_bravo",
        workshop_id: null,
        player_count: 0,
        max_players: 16,
        players: [],
        is_online: false,
        updated_at: "2026-03-12T10:00:00Z",
        state: {
          last_plugin_seen_at: "2026-03-12T10:00:00Z",
          last_a2s_seen_at: "2026-03-12T10:00:00Z",
          last_successful_seen_at: "2026-03-12T10:00:00Z",
        },
      },
    },
    {
      id: "019d3333-3333-7333-8333-333333333333",
      ip: "10.0.0.3",
      port: 27017,
      region: "EU",
      status: "enabled",
      configured_hostname: "Gamma Live",
      country: "DE",
      city: "Frankfurt",
      source: "manual",
      last_discovered_at: null,
      map_tier: 8,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group: {
        id: "019d0000-0000-7000-8000-000000000002",
        name: "Berlin Group",
      },
      live_status: {
        hostname: "Gamma Live",
        map: "kz_gamma",
        workshop_id: null,
        player_count: 7,
        max_players: 24,
        players: [
          {
            name: "Runner One",
            steamid64: "76561198000000001",
            mode: "kzt",
            score: 650,
            status: "in_progress",
            teleports: 2,
            timer_time: 142.5,
            duration_seconds: 412.25,
          },
        ],
        is_online: true,
        updated_at: "2026-03-12T10:00:00Z",
        state: {
          last_plugin_seen_at: "2026-03-12T10:00:00Z",
          last_a2s_seen_at: "2026-03-12T10:00:05Z",
          last_successful_seen_at: "2026-03-12T10:00:00Z",
        },
      },
    },
  ],
}

const updatedGammaServer = {
  type: "server.updated",
  server: {
    id: "019d3333-3333-7333-8333-333333333333",
    ip: "10.0.0.3",
    port: 27017,
    region: "EU",
    status: "enabled",
    configured_hostname: "Gamma Live Updated",
    country: "DE",
    city: "Frankfurt",
    source: "manual",
    last_discovered_at: null,
    map_tier: 8,
    created_at: "2026-03-12T10:00:00Z",
    updated_at: "2026-03-12T10:05:00Z",
    group: { id: "019d0000-0000-7000-8000-000000000002", name: "Berlin Group" },
    live_status: {
      hostname: "Gamma Live Updated",
      map: "kz_gamma",
      workshop_id: null,
      player_count: 9,
      max_players: 24,
      players: [
        {
          name: "Runner One",
          steamid64: "76561198000000001",
          mode: "kzt",
          score: 800,
          status: "finished",
          teleports: 2,
          timer_time: 155.4,
        },
      ],
      is_online: true,
      updated_at: "2026-03-12T10:05:00Z",
      state: {
        last_plugin_seen_at: "2026-03-12T10:05:00Z",
        last_a2s_seen_at: "2026-03-12T10:05:00Z",
        last_successful_seen_at: "2026-03-12T10:05:00Z",
      },
    },
  },
}

const addedServer = {
  id: "019d4444-4444-7444-8444-444444444444",
  ip: "10.0.0.4",
  port: 27018,
  region: "EU",
  status: "enabled",
  configured_hostname: "Delta Added",
  country: "FR",
  city: "Paris",
  source: "manual",
  last_discovered_at: null,
  map_tier: 4,
  created_at: "2026-03-12T10:10:00Z",
  updated_at: "2026-03-12T10:10:00Z",
  group: null,
  live_status: {
    hostname: "Delta Added",
    map: "bkz_delta",
    workshop_id: null,
    player_count: 4,
    max_players: 16,
    players: [],
    is_online: true,
    updated_at: "2026-03-12T10:10:00Z",
    state: {
      last_plugin_seen_at: null,
      last_a2s_seen_at: "2026-03-12T10:10:00Z",
      last_successful_seen_at: "2026-03-12T10:10:00Z",
    },
  },
}

const mapServers = {
  count: 4,
  data: [
    {
      id: "019d5555-5555-7555-8555-555555555555",
      ip: "10.1.1.1",
      port: 27015,
      latitude: 52.52,
      longitude: 13.405,
      region: "EU",
      status: "enabled",
      configured_hostname: "Shared Alpha A",
      country: "DE",
      city: "Berlin",
      source: "manual",
      last_discovered_at: null,
      map_tier: 2,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group: null,
      live_status: {
        hostname: "Shared Alpha A",
        map: "kz_alpha",
        workshop_id: null,
        player_count: 2,
        max_players: 16,
        players: [],
        is_online: true,
        updated_at: "2026-03-12T10:00:00Z",
        state: {
          last_plugin_seen_at: "2026-03-12T10:00:00Z",
          last_a2s_seen_at: "2026-03-12T10:00:00Z",
          last_successful_seen_at: "2026-03-12T10:00:00Z",
        },
      },
    },
    {
      id: "019d6666-6666-7666-8666-666666666666",
      ip: "10.1.1.2",
      port: 27016,
      latitude: 52.52,
      longitude: 13.405,
      region: "EU",
      status: "enabled",
      configured_hostname: "Shared Alpha B",
      country: "DE",
      city: "Berlin",
      source: "manual",
      last_discovered_at: null,
      map_tier: 3,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group: null,
      live_status: {
        hostname: "Shared Alpha B",
        map: "kz_beta",
        workshop_id: null,
        player_count: 1,
        max_players: 16,
        players: [],
        is_online: true,
        updated_at: "2026-03-12T10:00:00Z",
        state: {
          last_plugin_seen_at: "2026-03-12T10:00:00Z",
          last_a2s_seen_at: "2026-03-12T10:00:00Z",
          last_successful_seen_at: "2026-03-12T10:00:00Z",
        },
      },
    },
    {
      id: "019d7777-7777-7777-8777-777777777777",
      ip: "10.2.2.2",
      port: 27015,
      latitude: 41.8781,
      longitude: -87.6298,
      region: "NA",
      status: "enabled",
      configured_hostname: "Hidden Offline",
      country: "US",
      city: "Chicago",
      source: "manual",
      last_discovered_at: null,
      map_tier: 4,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group: null,
      live_status: {
        hostname: "Hidden Offline",
        map: "kz_hidden",
        workshop_id: null,
        player_count: 0,
        max_players: 16,
        players: [],
        is_online: false,
        updated_at: "2026-03-12T10:00:00Z",
        state: {
          last_plugin_seen_at: "2026-03-12T10:00:00Z",
          last_a2s_seen_at: "2026-03-12T10:00:00Z",
          last_successful_seen_at: "2026-03-12T10:00:00Z",
        },
      },
    },
    {
      id: "019d8888-8888-7888-8888-888888888888",
      ip: "10.3.3.3",
      port: 27015,
      latitude: null,
      longitude: null,
      region: "EU",
      status: "enabled",
      configured_hostname: "Unmapped Online",
      country: "FR",
      city: "Paris",
      source: "manual",
      last_discovered_at: null,
      map_tier: 5,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group: null,
      live_status: {
        hostname: "Unmapped Online",
        map: "kz_unmapped",
        workshop_id: null,
        player_count: 1,
        max_players: 16,
        players: [],
        is_online: true,
        updated_at: "2026-03-12T10:00:00Z",
        state: {
          last_plugin_seen_at: "2026-03-12T10:00:00Z",
          last_a2s_seen_at: "2026-03-12T10:00:00Z",
          last_successful_seen_at: "2026-03-12T10:00:00Z",
        },
      },
    },
  ],
}

async function readMapCanvasSample(page: Page) {
  return page
    .locator('[data-testid="server-world-map-chart"] canvas')
    .evaluate((canvasElement) => {
      const canvas = canvasElement as HTMLCanvasElement
      const context = canvas.getContext("2d")
      if (!context) {
        throw new Error("Map canvas 2D context was not available")
      }

      const { height, width } = canvas
      const imageData = context.getImageData(0, 0, width, height).data
      const sample: number[] = []

      for (let y = 0; y < height; y += 20) {
        for (let x = 0; x < width; x += 20) {
          const index = (y * width + x) * 4
          sample.push(
            imageData[index],
            imageData[index + 1],
            imageData[index + 2],
            imageData[index + 3],
          )
        }
      }

      return { height, sample, width }
    })
}

function getCanvasSampleDifference(
  left: Awaited<ReturnType<typeof readMapCanvasSample>>,
  right: Awaited<ReturnType<typeof readMapCanvasSample>>,
) {
  expect(left.width).toBe(right.width)
  expect(left.height).toBe(right.height)
  expect(left.sample).toHaveLength(right.sample.length)

  return left.sample.reduce(
    (total, value, index) => total + Math.abs(value - right.sample[index]),
    0,
  )
}

test("Public servers page supports live updates, filters, and route-bound details", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("gokz-datetime-format", "iso")

    const sockets: Array<{
      readyState: number
      onopen: ((event: Event) => void) | null
      onmessage: ((event: { data: string }) => void) | null
      onclose: ((event: Event) => void) | null
      onerror: ((event: Event) => void) | null
      dispatchMessage: (payload: unknown) => void
      close: () => void
      send: (_data?: unknown) => void
    }> = []

    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(_url: string) {
        sockets.push(this)
        queueMicrotask(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event("open"))
        })
      }

      send(_data?: unknown) {}

      close() {
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
      __mockServerSockets: sockets,
      __dispatchServerMessage: (payload: unknown) => {
        for (const socket of sockets) {
          socket.dispatchMessage(payload)
        }
      },
    })
  })

  await page.route(/\/v1\/servers\/(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seedServers),
    })
  })

  await page.goto("/servers")

  await expect(page).toHaveURL(/\/servers(\?.*)?$/)
  await expect.poll(() => new URL(page.url()).search).toBe("")
  await expect(page.getByRole("heading", { name: "Servers" })).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toBeVisible()
  await expect(
    page
      .getByTestId("server-card-10.0.0.1:27015")
      .getByRole("img", { name: "GlobalAPI records enabled" }),
  ).toBeVisible()
  await page
    .getByTestId("server-card-10.0.0.1:27015")
    .getByRole("img", { name: "GlobalAPI records enabled" })
    .hover()
  await expect(page.getByText("GlobalAPI check")).toBeVisible()
  await expect(page.getByText("Settings enforcer")).toBeVisible()
  await expect(page.getByText("KZT")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.2:27016")).toHaveCount(0)
  await expect(page.getByRole("button", { name: /All/ })).toBeVisible()
  await expect
    .poll(async () =>
      page
        .getByTestId("server-card-10.0.0.1:27015")
        .locator(".bg-cover")
        .first()
        .evaluate(
          (element) => window.getComputedStyle(element).backgroundImage,
        ),
    )
    .toContain("/v1/maps/workshop/123456789/preview-image")
  await expect
    .poll(async () =>
      page
        .getByTestId("server-card-10.0.0.1:27015")
        .locator(".bg-cover")
        .first()
        .evaluate(
          (element) => window.getComputedStyle(element).backgroundImage,
        ),
    )
    .toContain(
      "https://github.com/KZGlobalTeam/map-images/raw/public/webp/kz_seed.webp",
    )
  const seedCardBackground = await page
    .getByTestId("server-card-10.0.0.1:27015")
    .locator(".bg-cover")
    .first()
    .evaluate((element) => window.getComputedStyle(element).backgroundImage)
  const staticSeedImageUrl =
    "https://github.com/KZGlobalTeam/map-images/raw/public/webp/kz_seed.webp"
  const workshopSeedImagePath = "/v1/maps/workshop/123456789/preview-image"
  expect(seedCardBackground.indexOf(staticSeedImageUrl)).toBeLessThan(
    seedCardBackground.indexOf(workshopSeedImagePath),
  )

  await page.waitForFunction(() => {
    return (
      Array.isArray((window as any).__mockServerSockets) &&
      (window as any).__mockServerSockets.length > 0
    )
  })

  await page.evaluate((payload) => {
    ;(window as any).__dispatchServerMessage(payload)
  }, snapshotServers)

  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.2:27016")).toHaveCount(0)
  await expect(page.getByText("12 Players")).toBeVisible()
  await expect(page.getByText("2 Servers")).toBeVisible()
  await expect(page.getByTitle("Refreshing server status")).toHaveCount(1)
  await expect
    .poll(async () =>
      page
        .getByTestId("server-card-10.0.0.3:27017")
        .locator(".bg-cover")
        .first()
        .evaluate(
          (element) => window.getComputedStyle(element).backgroundImage,
        ),
    )
    .toBe(
      'url("https://github.com/KZGlobalTeam/map-images/raw/public/webp/kz_gamma.webp")',
    )

  await page.evaluate((server) => {
    ;(window as any).__dispatchServerMessage({
      server,
      type: "server.updated",
    })
  }, addedServer)

  await expect(page.getByRole("button", { name: /Others/ })).toBeVisible()
  await page.getByRole("button", { name: /Others/ }).click()
  await expect(page).toHaveURL(/\/servers\/group\/others$/)
  await expect(page.getByTestId("server-card-10.0.0.4:27018")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toHaveCount(0)
  await page.getByRole("button", { name: /Others/ }).click()

  const hoverCard = page.getByTestId("server-card-10.0.0.3:27017")
  await hoverCard.hover()
  await page.waitForTimeout(250)
  const hoveredBoxShadow = await hoverCard.evaluate((element) => {
    return window.getComputedStyle(element).boxShadow
  })
  expect(hoveredBoxShadow).not.toBe("none")

  await page.getByRole("button", { name: "Online" }).click()
  await expect(page.getByTestId("server-card-10.0.0.2:27016")).toBeVisible()

  await page.getByRole("button", { name: /(EU|Europe)/ }).click()
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toHaveCount(0)
  await expect(page.getByTestId("server-card-10.0.0.2:27016")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toHaveCount(0)

  await page.getByRole("button", { name: "Online" }).click()
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toBeVisible()

  const searchInput = page.getByPlaceholder(
    "Search IP, hostname, map, city, group...",
  )
  await searchInput.fill("Gamma Live")
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.2:27016")).toHaveCount(0)

  await searchInput.fill("10.0.0.3:27017")
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toBeVisible()

  await searchInput.fill("")
  await page
    .getByTestId("server-card-10.0.0.3:27017")
    .getByTitle("Gamma Live")
    .click()
  await expect(page).toHaveURL(/\/servers(\?|$)/)

  await page.getByRole("link", { name: /\[kzt\]Runner One/ }).click()
  await expect(page).toHaveURL(/\/profile\/76561198000000001$/)
  await page.goBack()
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toBeVisible()

  await page.getByTestId("server-card-map-image-10.0.0.3:27017").click()

  await expect(page).toHaveURL(/\/servers\/10\.0\.0\.3:27017(\?|$)/)
  await expect
    .poll(() => new URL(page.url()).searchParams.get("status"))
    .toBeNull()
  await expect
    .poll(() => new URL(page.url()).searchParams.get("region"))
    .toBeNull()
  await expect
    .poll(() => new URL(page.url()).searchParams.get("view"))
    .toBeNull()
  await expect
    .poll(() => new URL(page.url()).searchParams.get("sort"))
    .toBeNull()
  await expect
    .poll(() => new URL(page.url()).searchParams.get("dir"))
    .toBeNull()
  await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBeNull()
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toBeVisible()
  await expect(
    page.getByRole("columnheader", { name: "Duration" }),
  ).toBeVisible()
  await expect(page.getByRole("cell", { name: "6:52" })).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toHaveClass(
    /server-selected_650ms_ease-out/,
  )

  await page.evaluate((payload) => {
    ;(window as any).__dispatchServerMessage(payload)
  }, updatedGammaServer)

  await expect(page.getByText("Gamma Live Updated").first()).toBeVisible()
  await expect(page.getByText("9/24").first()).toBeVisible()
  await expect(page.getByTitle("Refreshing server status")).toHaveCount(0)
})

test("Public servers map aggregates loaded servers by city", async ({
  page,
}) => {
  await page.addInitScript(() => {
    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      readyState = MockWebSocket.OPEN
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(_url: string) {
        queueMicrotask(() => {
          this.onopen?.(new Event("open"))
        })
      }

      send(_data?: unknown) {}
      close() {}
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      value: MockWebSocket,
    })
  })

  await page.route(/\/v1\/servers(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mapServers),
    })
  })

  await page.goto("/servers")

  await expect(page.getByTestId("server-card-10.1.1.1:27015")).toBeVisible()
  await expect(page.getByTestId("server-card-10.2.2.2:27015")).toHaveCount(0)

  await page.getByTestId("open-servers-map-button").click()

  await expect(page.getByRole("heading", { name: "Server map" })).toBeVisible()
  await expect(page.getByTestId("server-world-map-chart")).toBeVisible()
  const chartBox = await page
    .getByTestId("server-world-map-chart")
    .boundingBox()
  const canvasBox = await page
    .locator('[data-testid="server-world-map-chart"] canvas')
    .boundingBox()
  expect(chartBox).not.toBeNull()
  expect(canvasBox).not.toBeNull()
  expect(Math.abs(chartBox!.width - canvasBox!.width)).toBeLessThanOrEqual(16)
  expect(Math.abs(chartBox!.height - canvasBox!.height)).toBeLessThanOrEqual(16)
  expect(chartBox!.width / chartBox!.height).toBeGreaterThan(1.9)
  expect(chartBox!.width / chartBox!.height).toBeLessThan(1.98)
  await expect(page.getByText(/mapped online servers/)).toHaveCount(0)
  await expect(page.getByText(/without coordinates/)).toHaveCount(0)
  await expect(page.locator('[data-testid^="server-map-ip-row-"]')).toHaveCount(
    0,
  )
})

test("Public servers map keeps user zoom after live server updates", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const sockets: Array<{
      readyState: number
      onopen: ((event: Event) => void) | null
      onmessage: ((event: { data: string }) => void) | null
      onclose: ((event: Event) => void) | null
      onerror: ((event: Event) => void) | null
      dispatchMessage: (payload: unknown) => void
      close: () => void
      send: (_data?: unknown) => void
    }> = []

    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(_url: string) {
        sockets.push(this)
        queueMicrotask(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event("open"))
        })
      }

      send(_data?: unknown) {}

      close() {
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
      __mockServerSockets: sockets,
      __dispatchServerMessage: (payload: unknown) => {
        for (const socket of sockets) {
          socket.dispatchMessage(payload)
        }
      },
    })
  })

  await page.route(/\/v1\/servers(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mapServers),
    })
  })

  await page.goto("/servers")
  await page.getByTestId("open-servers-map-button").click()
  await page.locator('[data-testid="server-world-map-chart"] canvas').waitFor({
    state: "visible",
  })

  const initialCanvas = await readMapCanvasSample(page)
  const chartBox = await page
    .getByTestId("server-world-map-chart")
    .boundingBox()
  expect(chartBox).not.toBeNull()

  await page.mouse.move(
    chartBox!.x + chartBox!.width / 2,
    chartBox!.y + chartBox!.height / 2,
  )
  await page.mouse.wheel(0, -900)
  await page.waitForTimeout(300)
  const zoomedCanvas = await readMapCanvasSample(page)
  const zoomDifference = getCanvasSampleDifference(initialCanvas, zoomedCanvas)
  expect(zoomDifference).toBeGreaterThan(1_000)

  await page.evaluate((server) => {
    ;(window as any).__dispatchServerMessage({
      server: {
        ...server,
        live_status: {
          ...server.live_status,
          player_count: 3,
          updated_at: "2026-03-12T10:05:00Z",
        },
        updated_at: "2026-03-12T10:05:00Z",
      },
      type: "server.updated",
    })
  }, mapServers.data[0])

  await page.waitForTimeout(300)
  const afterUpdateCanvas = await readMapCanvasSample(page)
  const updateDifference = getCanvasSampleDifference(
    zoomedCanvas,
    afterUpdateCanvas,
  )

  expect(updateDifference).toBeLessThan(zoomDifference * 0.25)
})

test("Public servers page downloads a generic config for the visible sorted servers", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const sockets: Array<{
      readyState: number
      onopen: ((event: Event) => void) | null
      onmessage: ((event: { data: string }) => void) | null
      onclose: ((event: Event) => void) | null
      onerror: ((event: Event) => void) | null
      dispatchMessage: (payload: unknown) => void
      close: () => void
      send: (_data?: unknown) => void
    }> = []

    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(_url: string) {
        sockets.push(this)
        queueMicrotask(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event("open"))
        })
      }

      send(_data?: unknown) {}

      close() {
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
      __mockServerSockets: sockets,
      __dispatchServerMessage: (payload: unknown) => {
        for (const socket of sockets) {
          socket.dispatchMessage(payload)
        }
      },
    })
  })

  await page.route(/\/v1\/servers\/(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: snapshotServers.servers.length,
        data: snapshotServers.servers,
      }),
    })
  })

  await page.goto("/servers")
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toBeVisible()

  await page
    .getByPlaceholder("Search IP, hostname, map, city, group...")
    .fill("kz_")

  const downloadPromise = page.waitForEvent("download")
  await page.getByTestId("download-servers-config-button").click()
  const download = await downloadPromise

  expect(download.suggestedFilename()).toBe("servers.cfg")

  const downloadPath = await download.path()
  expect(downloadPath).not.toBeNull()

  const configContent = await readFile(downloadPath!, "utf8")

  expect(configContent).toContain("// GOKZ.TOP public servers config")
  expect(configContent).toContain("// Run: exec servers.cfg")
  expect(configContent).toContain('echo "GOKZ.TOP server aliases loaded:"')
  expect(configContent).toContain("// 1. Alpha Seed")
  expect(configContent).toContain('echo "1. Alpha Seed"')
  expect(configContent).toContain('alias "s1" "connect 10.0.0.1:27015"')
  expect(configContent).toContain("// 2. Gamma Live")
  expect(configContent).toContain('echo "2. Gamma Live"')
  expect(configContent).toContain('alias "s2" "connect 10.0.0.3:27017"')
  expect(configContent).not.toContain("Bravo Offline")
  expect(configContent).not.toContain("10.0.0.2:27016")
  expect(configContent).not.toContain("kz_seed")
  expect(configContent).not.toContain("kz_gamma")
  expect(configContent).not.toContain("Seed Group")
  expect(configContent).not.toContain("Berlin Group")
  expect(configContent).not.toContain("online")
  expect(configContent).not.toContain("offline")
  expect(configContent).not.toContain("AXE")
  expect(configContent).not.toContain("axekz")

  await expect(
    page.getByRole("heading", { name: "Server config downloaded" }),
  ).toBeVisible()
  await expect(
    page.getByText(
      "The file includes the servers currently visible in this browser, sorted by hostname.",
    ),
  ).toBeVisible()
})

test("Add server button prompts for Steam login when logged out", async ({
  page,
}) => {
  await page.addInitScript(() => {
    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      readyState = MockWebSocket.OPEN
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(_url: string) {
        queueMicrotask(() => {
          this.onopen?.(new Event("open"))
        })
      }

      send(_data?: unknown) {}
      close() {}
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      value: MockWebSocket,
    })
  })

  await page.route(/\/v1\/servers\/(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seedServers),
    })
  })

  await page.goto("/servers")

  await page.getByTestId("add-server-button").click()

  await expect(page.getByRole("heading", { name: "Add Server" })).toBeVisible()
  await expect(page.getByText("Login required")).toBeVisible()
  await expect(
    page.getByText("You need to log in with Steam before adding a server."),
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Continue with Steam" }),
  ).toBeVisible()
})

test("Logged-in users can add a server from the servers page", async ({
  page,
}) => {
  await page.addInitScript(() => {
    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      readyState = MockWebSocket.OPEN
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(_url: string) {
        queueMicrotask(() => {
          this.onopen?.(new Event("open"))
        })
      }

      send(_data?: unknown) {}
      close() {}
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      value: MockWebSocket,
    })
  })
  await logInUser(page, randomSteamid64())

  await page.route(/\/v1\/servers\/(\?.*)?$/, async (route) => {
    if (route.request().method() === "POST") {
      expect(route.request().postDataJSON()).toEqual({
        ip: "10.0.0.4",
        port: 27018,
        status: "enabled",
      })
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(addedServer),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seedServers),
    })
  })

  await page.goto("/servers")

  await page.getByTestId("add-server-button").click()
  await expect(page.getByRole("heading", { name: "Add Server" })).toBeVisible()
  await page.getByTestId("add-server-address-input").fill("10.0.0.4:27018")
  await page.getByRole("button", { name: "Add" }).click()

  await expect(page.getByTestId("server-card-10.0.0.4:27018")).toBeVisible()
  await expect(page.getByText("Delta Added")).toBeVisible()
})
