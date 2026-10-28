import { readFile } from "node:fs/promises"
import type { Page } from "@playwright/test"
import { expect, test } from "@playwright/test"
import { stubMapImageAssets } from "./utils/mapImages"
import { randomSteamid64 } from "./utils/random"
import { logInUser } from "./utils/user"

test.use({ storageState: { cookies: [], origins: [] } })

async function stubMapImageGraphql(
  page: Page,
  onBatch?: (
    inputs: Array<{ mapName: string; workshopId: string | null }>,
  ) => void,
) {
  await stubMapImageAssets(page)
  await page.route("**/v1/graphql", async (route) => {
    const body = route.request().postDataJSON() as {
      query?: string
      variables?: {
        inputs?: Array<{ mapName: string; workshopId?: string | null }>
      }
    }
    if (!body.query?.includes("query MapImages")) {
      await route.fallback()
      return
    }

    const inputs = (body.variables?.inputs ?? []).map((input) => ({
      mapName: input.mapName,
      workshopId: input.workshopId ?? null,
    }))
    onBatch?.(inputs)
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          mapImages: inputs.map((input) => ({
            ...input,
            previewUrl:
              input.mapName === "kz_seed" && input.workshopId
                ? `https://steam.example/${input.workshopId}.jpg`
                : `${new URL(route.request().url()).origin}/v1/maps/images/${encodeURIComponent(input.mapName)}.webp`,
          })),
        },
      }),
    })
  })
}

const seedServers = {
  count: 1,
  data: [
    {
      id: "019d1111-1111-7111-8111-111111111111",
      ip: "10.0.0.1",
      port: 27015,
      region: "NA",
      status: "enabled",
      is_public: true,
      configured_hostname: "Alpha Seed",
      country: "US",
      city: "Chicago",
      source: "manual",
      last_discovered_at: null,
      map_tier: 2,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group_id: "019d0000-0000-7000-8000-000000000001",
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
      is_public: true,
      configured_hostname: "Bravo Offline",
      country: "DE",
      city: "Berlin",
      source: "manual",
      last_discovered_at: null,
      map_tier: 7,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group_id: "019d0000-0000-7000-8000-000000000002",
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
      is_public: true,
      configured_hostname: "Gamma Live",
      country: "DE",
      city: "Frankfurt",
      source: "manual",
      last_discovered_at: null,
      map_tier: 8,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T10:00:00Z",
      group_id: "019d0000-0000-7000-8000-000000000002",
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
        sv_ms: 0.428,
        var_ms: 0.016,
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
            ping_ms: 34,
          },
          {
            name: "Runner Missing Ping",
            steamid64: "76561198000000002",
            mode: "vnl",
            score: 500,
            status: "finished",
            teleports: 0,
            timer_time: 180,
            duration_seconds: 200,
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
    is_public: true,
    configured_hostname: "Gamma Live Updated",
    country: "DE",
    city: "Frankfurt",
    source: "manual",
    last_discovered_at: null,
    map_tier: 8,
    created_at: "2026-03-12T10:00:00Z",
    updated_at: "2026-03-12T10:05:00Z",
    group_id: "019d0000-0000-7000-8000-000000000002",
    group: { id: "019d0000-0000-7000-8000-000000000002", name: "Berlin Group" },
    live_status: {
      hostname: "Gamma Live Updated",
      map: "kz_gamma",
      workshop_id: null,
      player_count: 9,
      max_players: 24,
      sv_ms: 0.615,
      var_ms: 0.024,
      players: [
        {
          name: "Runner One",
          steamid64: "76561198000000001",
          mode: "kzt",
          score: 800,
          status: "finished",
          teleports: 2,
          timer_time: 155.4,
          ping_ms: 41,
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
  is_public: true,
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
      is_public: true,
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
      is_public: true,
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
      is_public: true,
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
      is_public: true,
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

test("Server details show rich telemetry and update legacy snapshots", async ({
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

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new Event("close"))
      }

      send(_data?: unknown) {}

      dispatchMessage(payload: unknown) {
        this.onmessage?.({ data: JSON.stringify(payload) })
      }
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      value: MockWebSocket,
    })
    Object.assign(window, {
      __dispatchServerMessage: (payload: unknown) => {
        for (const socket of sockets) {
          socket.dispatchMessage(payload)
        }
      },
    })
  })

  await page.route(/\/v1\/servers\/?(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: snapshotServers.servers.length,
        data: snapshotServers.servers,
      }),
    })
  })

  await page.goto("/servers/10.0.0.3:27017")

  await expect(page.getByRole("columnheader", { name: "Ping" })).toBeVisible()
  await expect(page.getByRole("cell", { name: "34 ms" })).toBeVisible()
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "Runner Missing Ping" })
      .getByText("-"),
  ).toBeVisible()
  await expect(page.getByText("SV 0.428 ms")).toBeVisible()
  await expect(page.getByText("VAR 0.016 ms")).toBeVisible()

  await page.evaluate((payload) => {
    ;(window as any).__dispatchServerMessage(payload)
  }, updatedGammaServer)

  await expect(page.getByRole("cell", { name: "41 ms" })).toBeVisible()
  await expect(page.getByText("SV 0.615 ms")).toBeVisible()
  await expect(page.getByText("VAR 0.024 ms")).toBeVisible()

  const legacyServer = {
    ...updatedGammaServer.server,
    live_status: {
      ...updatedGammaServer.server.live_status,
      sv_ms: undefined,
      var_ms: undefined,
      players: updatedGammaServer.server.live_status.players.map(
        ({ ping_ms: _pingMs, ...player }) => player,
      ),
    },
  }
  await page.evaluate((server) => {
    ;(window as any).__dispatchServerMessage({ type: "server.updated", server })
  }, legacyServer)

  await expect(page.getByRole("columnheader", { name: "Ping" })).toHaveCount(0)
  await expect(page.getByText(/^SV /)).toHaveCount(0)
  await expect(page.getByText(/^VAR /)).toHaveCount(0)
})

test("Public servers page supports live updates, filters, and route-bound details", async ({
  page,
}) => {
  const mapImageBatches: Array<
    Array<{ mapName: string; workshopId: string | null }>
  > = []
  const previewRedirectRequests: string[] = []
  await stubMapImageGraphql(page, (inputs) => mapImageBatches.push(inputs))
  page.on("request", (request) => {
    if (/\/v1\/maps\/(?:workshop\/[^/]+\/)?preview-image/.test(request.url())) {
      previewRedirectRequests.push(request.url())
    }
  })
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
          const snapshot = (window as any).__latestServerSnapshot
          if (snapshot) this.dispatchMessage(snapshot)
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
        if ((payload as any)?.type === "server.snapshot")
          (window as any).__latestServerSnapshot = payload
        for (const socket of sockets) {
          socket.dispatchMessage(payload)
        }
      },
    })
  })

  await page.route(/\/v1\/servers\/?(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seedServers),
    })
  })

  await page.goto("/servers")

  await expect(page).toHaveURL(/\/servers(\?.*)?$/)
  await expect.poll(() => new URL(page.url()).search).toBe("")
  await expect(
    page.getByRole("textbox", { name: "Search servers" }),
  ).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toBeVisible()
  await expect(
    page.getByTestId("server-card-10.0.0.1:27015").getByRole("img", {
      name: "Records enabled through GlobalAPI or gokz.top",
    }),
  ).toBeVisible()
  await page
    .getByTestId("server-card-10.0.0.1:27015")
    .getByRole("img", { name: "Records enabled through GlobalAPI or gokz.top" })
    .hover()
  await expect(page.getByRole("tooltip")).toBeVisible()
  await expect(page.getByText("Settings enforcer").first()).toBeVisible()
  await expect(page.getByText("KZT").first()).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.2:27016")).toHaveCount(0)
  await expect(page.getByRole("button", { name: /Seed Group/ })).toBeVisible()
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
    .toContain("https://steam.example/123456789.jpg")
  const seedCardBackground = await page
    .getByTestId("server-card-10.0.0.1:27015")
    .locator(".bg-cover")
    .first()
    .evaluate((element) => window.getComputedStyle(element).backgroundImage)
  expect(seedCardBackground).toBe('url("https://steam.example/123456789.jpg")')
  await expect.poll(() => mapImageBatches.length).toBe(1)
  expect(mapImageBatches[0]).toEqual([
    { mapName: "kz_seed", workshopId: "123456789" },
  ])
  expect(previewRedirectRequests).toEqual([])

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

  const hideEmpty = page.getByRole("button", {
    name: "Hide empty",
    exact: true,
  })
  const hideOccupied = page.getByRole("button", {
    name: "Hide occupied",
    exact: true,
  })
  await expect(hideEmpty).toHaveAttribute("aria-pressed", "false")
  await expect(hideOccupied).toHaveAttribute("aria-pressed", "false")
  await hideEmpty.click()
  await expect(hideEmpty).toHaveAttribute("aria-pressed", "true")
  await expect(page.getByText("2 Servers")).toBeVisible()

  // A live server becomes empty while the filter is active.
  await page.evaluate((server) => {
    ;(window as any).__dispatchServerMessage({
      type: "server.updated",
      server: {
        ...server,
        live_status: { ...server.live_status, player_count: 0, players: [] },
      },
    })
  }, snapshotServers.servers[2])
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toHaveCount(0)
  await expect(page.getByText("1 Server", { exact: true })).toBeVisible()
  await hideOccupied.click()
  await expect(hideEmpty).toHaveAttribute("aria-pressed", "false")
  await expect(hideOccupied).toHaveAttribute("aria-pressed", "true")
  await expect(page.getByTestId("server-card-10.0.0.3:27017")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toHaveCount(0)
  await page.getByRole("button", { name: "Table view" }).click()
  await expect(
    page.getByRole("cell", { name: "Gamma Live", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("cell", { name: "Alpha Seed", exact: true }),
  ).toHaveCount(0)
  await hideOccupied.click()
  await expect(
    page.getByRole("cell", { name: "Alpha Seed", exact: true }),
  ).toBeVisible()
  await page.getByRole("button", { name: "Grid view" }).click()
  await page.evaluate((payload) => {
    ;(window as any).__dispatchServerMessage(payload)
  }, snapshotServers)
  await expect(page.getByText("12 Players")).toBeVisible()
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
    .toMatch(/url\("https?:\/\/[^" ]+\/v1\/maps\/images\/kz_gamma\.webp"\)/)

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

  const searchInput = page.getByRole("textbox", { name: "Search servers" })
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

test("Public servers page removes a hidden server from live updates", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const sockets: Array<{
      onopen: ((event: Event) => void) | null
      onmessage: ((event: { data: string }) => void) | null
      onclose: ((event: Event) => void) | null
      onerror: ((event: Event) => void) | null
      close: () => void
      send: (_data?: unknown) => void
    }> = []

    class MockWebSocket {
      static OPEN = 1
      readyState = MockWebSocket.OPEN
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(_url: string) {
        sockets.push(this)
        queueMicrotask(() => this.onopen?.(new Event("open")))
      }

      send(_data?: unknown) {}
      close() {}
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      value: MockWebSocket,
    })
    Object.assign(window, {
      __dispatchServerRemoved: (serverId: string) => {
        for (const socket of sockets) {
          socket.onmessage?.({
            data: JSON.stringify({
              type: "server.removed",
              server_id: serverId,
            }),
          })
        }
      },
    })
  })
  await page.route(/\/v1\/servers(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seedServers),
    })
  })

  await page.goto("/servers")
  const serverCard = page.getByTestId("server-card-10.0.0.1:27015")
  await expect(serverCard).toBeVisible()

  await page.evaluate((serverId) => {
    ;(window as any).__dispatchServerRemoved(serverId)
  }, seedServers.data[0].id)

  await expect(serverCard).toHaveCount(0)
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

  await page.route(/\/v1\/servers\/?(\?.*)?$/, async (route) => {
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

  await page.getByRole("textbox", { name: "Search servers" }).fill("kz_")

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

  await page.route(/\/v1\/servers\/?(\?.*)?$/, async (route) => {
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

  await page.route(/\/v1\/servers\/?(\?.*)?$/, async (route) => {
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

test("Russian servers have an RU filter separate from other CIS servers", async ({
  page,
}) => {
  await page.routeWebSocket("**/v1/ws/servers", () => {})
  await stubMapImageGraphql(page)
  const russianServer = {
    ...seedServers.data[0],
    id: "019d4444-4444-7444-8444-444444444444",
    ip: "10.0.0.4",
    region: "CIS",
    country: "RU",
    city: "Moscow",
  }
  const otherCisServer = {
    ...russianServer,
    id: "019d5555-5555-7555-8555-555555555555",
    ip: "10.0.0.5",
    country: "KZ",
    city: "Almaty",
    live_status: { ...russianServer.live_status, player_count: 3 },
  }
  await page.route(/\/v1\/servers\/?(\?.*)?$/, async (route) => {
    await route.fulfill({
      json: {
        count: 3,
        data: [...seedServers.data, russianServer, otherCisServer],
      },
    })
  })
  await page.goto("/servers")
  const ruFilter = page.getByRole("button", { name: /RU \(5\)/ })
  const cisFilter = page.getByRole("button", { name: /CIS \(3\)/ })
  await expect(
    ruFilter.getByRole("img", { name: "Russia", exact: true }),
  ).toBeVisible()
  await expect(cisFilter.locator("img")).toHaveAttribute(
    "src",
    /Flag_of_the_CIS/,
  )
  await page.screenshot({ path: "../.temp/screenshots/servers-ru-flag.png" })
  await ruFilter.click()
  await expect(page.getByTestId("server-card-10.0.0.4:27015")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.5:27015")).toHaveCount(0)
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toHaveCount(0)
  await page.reload()
  await expect(page.getByTestId("server-card-10.0.0.4:27015")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.5:27015")).toHaveCount(0)
  await cisFilter.click()
  await expect(page.getByTestId("server-card-10.0.0.5:27015")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.4:27015")).toHaveCount(0)
  await cisFilter.click()
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toBeVisible()
  await expect(page.getByTestId("server-card-10.0.0.4:27015")).toBeVisible()
})

for (const scenario of [
  { global: true, top: false, online: true, green: true },
  { global: false, top: true, online: true, green: true },
  { global: false, top: false, online: true, green: false },
  { global: true, top: true, online: false, green: false },
]) {
  test(`records globe: GlobalAPI=${scenario.global} gokz.top=${scenario.top} online=${scenario.online}`, async ({
    page,
  }) => {
    await stubMapImageGraphql(page)
    const server = structuredClone(seedServers.data[0])
    const status = server.live_status.global_status
    server.live_status.is_online = scenario.online
    server.live_status.global_status = {
      ...status,
      api_key_valid: scenario.global,
      eligible: scenario.global,
    }
    const response = {
      ...server,
      live_status: {
        ...server.live_status,
        gokz_top_status: {
          ...status,
          api_key_valid: scenario.top,
          eligible: scenario.top,
          modes: { KZT: false, SKZ: false, VNL: false, NKZ: scenario.top },
        },
      },
    }
    await page.route(/\/v1\/servers\/?(\?.*)?$/, (route) =>
      route.fulfill({ json: { data: [response], count: 1 } }),
    )
    await page.goto("/servers")
    if (!scenario.online)
      await page.getByRole("button", { name: "Online", exact: true }).click()
    const badge = page
      .getByTestId("server-card-10.0.0.1:27015")
      .getByRole("img", {
        name: scenario.green
          ? "Records enabled through GlobalAPI or gokz.top"
          : "GlobalAPI and gokz.top records unavailable or unchecked",
      })
    await expect(badge).toHaveClass(
      scenario.green ? /bg-emerald-500/ : /bg-red-500/,
    )
    await badge.hover()
    const tooltip = page.getByRole("tooltip")
    await expect(tooltip.getByText("GlobalAPI", { exact: true })).toBeVisible()
    await expect(tooltip.getByText("gokz.top", { exact: true })).toBeVisible()
    await expect(tooltip.getByText("NKZ", { exact: true })).toBeVisible()
  })
}

test("Server occupancy filters round-trip through share links", async ({
  page,
}) => {
  await stubMapImageGraphql(page)
  await page.routeWebSocket("**/v1/ws/servers**", () => {})
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: async (value: string) => {
          ;(window as any).__copiedServerLink = value
        },
      },
    })
  })
  await page.route(/\/v1\/servers\/?(\?.*)?$/, async (route) => {
    await route.fulfill({ json: seedServers })
  })
  await page.goto("/servers?hide_empty=true&hide_occupied=false")
  const hideEmpty = page.getByRole("button", {
    name: "Hide empty",
    exact: true,
  })
  const hideOccupied = page.getByRole("button", {
    name: "Hide occupied",
    exact: true,
  })
  await expect(hideEmpty).toHaveAttribute("aria-pressed", "true")
  await expect(hideOccupied).toHaveAttribute("aria-pressed", "false")
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toBeVisible()
  await hideOccupied.click()
  await expect(hideEmpty).toHaveAttribute("aria-pressed", "false")
  await expect(hideOccupied).toHaveAttribute("aria-pressed", "true")
  await hideEmpty.click()
  await expect(hideOccupied).toHaveAttribute("aria-pressed", "false")
  await hideOccupied.click()
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toHaveCount(0)
  await page.getByRole("button", { name: "Copy share link" }).click()
  await expect
    .poll(() => page.evaluate(() => (window as any).__copiedServerLink))
    .toBeTruthy()
  const shareLink = await page.evaluate(
    () => (window as any).__copiedServerLink as string,
  )
  expect(new URL(shareLink).searchParams.get("hide_empty")).toBe("false")
  expect(new URL(shareLink).searchParams.get("hide_occupied")).toBe("true")
  await page.goto(shareLink)
  await expect(hideEmpty).toHaveAttribute("aria-pressed", "false")
  await expect(hideOccupied).toHaveAttribute("aria-pressed", "true")
  await expect(page.getByText("0 Servers")).toBeVisible()
  const filterBox = await hideOccupied.boundingBox()
  const actionBox = await page
    .getByRole("button", { name: "Open server map" })
    .boundingBox()
  expect(filterBox).not.toBeNull()
  expect(actionBox).not.toBeNull()
  expect(actionBox!.y).toBeGreaterThanOrEqual(filterBox!.y + filterBox!.height)
  await page.screenshot({
    path: "../.temp/screenshots/server-filter-rows.png",
    fullPage: true,
  })

  // Old links that enabled both filters must still produce a valid selection.
  await page.goto("/servers?hide_empty=true&hide_occupied=true")
  await expect(hideEmpty).toHaveAttribute("aria-pressed", "true")
  await expect(hideOccupied).toHaveAttribute("aria-pressed", "false")
  await expect(page.getByTestId("server-card-10.0.0.1:27015")).toBeVisible()
})

for (const locale of ["zh-CN", "ru"] as const) {
  test(`Server browser translates controls, tooltips, and dialogs in ${locale}`, async ({
    page,
  }) => {
    const { resources } = await import("../src/i18n/resources")
    const messages = resources[locale].translation
    const copy = messages.serverBrowser
    await page.addInitScript(
      (language) => localStorage.setItem("gokz-language", language),
      locale,
    )
    await page.routeWebSocket("**/v1/ws/servers**", () => {})
    await stubMapImageGraphql(page)
    await page.route(/\/v1\/servers\/?(\?.*)?$/, (route) =>
      route.fulfill({
        json: {
          ...seedServers,
          data: seedServers.data.map((server) => ({
            ...server,
            live_status: {
              ...server.live_status,
              players: [
                {
                  name: "Translation Runner",
                  status: "in_progress",
                  stage: 0,
                  timer_time: 42,
                  duration_seconds: 60,
                },
              ],
            },
          })),
        },
      }),
    )
    await page.goto("/servers")
    await expect(page.getByPlaceholder(copy.searchPlaceholder)).toBeVisible()
    await expect(
      page.getByRole("button", { name: copy.hideEmpty, exact: true }),
    ).toHaveAttribute("title", copy.hideEmptyTooltip)
    await expect(
      page.getByRole("button", { name: copy.hideOccupied, exact: true }),
    ).toHaveAttribute("title", copy.hideOccupiedTooltip)
    await expect(
      page.getByText(locale === "ru" ? "5 игроков" : "5 玩家", {
        exact: true,
      }),
    ).toBeVisible()
    await expect(
      page.getByText(locale === "ru" ? "1 сервер" : "1 服务器", {
        exact: true,
      }),
    ).toBeVisible()
    await page.screenshot({
      path: `../.temp/screenshots/servers-${locale}-grid.png`,
      fullPage: true,
    })
    const card = page.getByTestId("server-card-10.0.0.1:27015")
    await expect(
      card.getByRole("button", { name: copy.copyAddress }),
    ).toHaveAttribute("title", copy.copyAddress)
    await card
      .getByRole("img", { name: messages.serverGlobalStatus.eligibleAria })
      .hover()
    await expect(
      page
        .getByRole("tooltip")
        .getByText(messages.serverGlobalStatus.apiKey, { exact: true })
        .first(),
    ).toBeVisible()
    await expect(
      page.getByRole("tooltip").getByLabel(copy.passed).first(),
    ).toBeVisible()
    await page
      .getByRole("button", { name: copy.tableView, exact: true })
      .click()
    for (const label of [copy.server, copy.map, copy.tier, copy.players]) {
      await expect(
        page
          .getByRole("columnheader")
          .getByRole("button", { name: label, exact: true }),
      ).toBeVisible()
    }
    await page
      .getByTestId("server-row-10.0.0.1:27015")
      .getByText("Alpha Seed", { exact: true })
      .click()
    const dialog = page.getByRole("dialog")
    await expect(
      dialog.getByRole("columnheader", { name: copy.duration, exact: true }),
    ).toBeVisible()
    await expect(
      dialog.getByText(copy.inProgress, { exact: true }),
    ).toBeVisible()
    await expect(dialog.getByText(copy.main, { exact: true })).toBeVisible()
    await dialog
      .getByRole("button", { name: messages.common.close, exact: true })
      .click()
    await page.getByTestId("add-server-button").click()
    await expect(
      dialog.getByRole("heading", { name: copy.addTitle, exact: true }),
    ).toBeVisible()
    await expect(
      dialog.getByText(copy.addLoginDescription, { exact: true }),
    ).toBeVisible()
    await dialog
      .getByRole("button", { name: messages.common.cancel, exact: true })
      .click()
    const download = page.waitForEvent("download")
    await page.getByTestId("download-servers-config-button").click()
    await download
    await expect(
      dialog.getByRole("heading", { name: copy.configTitle }),
    ).toBeVisible()
    await expect(
      dialog.getByText(copy.configDescription, { exact: true }),
    ).toBeVisible()
    await expect(
      dialog.locator("code").filter({ hasText: "autoexec.cfg" }),
    ).toBeVisible()
    await dialog
      .getByRole("button", { name: messages.common.close, exact: true })
      .click()
    await page.getByTestId("open-servers-map-button").click()
    await expect(
      dialog.getByRole("heading", { name: copy.worldMapTitle }),
    ).toBeVisible()
    await expect(
      dialog.getByText(copy.noCoordinates, { exact: true }),
    ).toBeVisible()
    await page.screenshot({
      path: `../.temp/screenshots/servers-${locale}-dialog.png`,
    })
  })
}

test("Add-server validation and API errors are translated", async ({
  page,
}) => {
  await page.route("**/v1/me/notifications/unread-count", (route) =>
    route.fulfill({ json: { count: 0 } }),
  )
  await page.route("**/v1/admin/servers/access", (route) =>
    route.fulfill({ json: { can_access: false } }),
  )
  await page.route("**/v1/players/76561198000000001*", (route) =>
    route.fulfill({
      json: { steamid64: "76561198000000001", name: "Translation Tester" },
    }),
  )

  await page.addInitScript(() => {
    localStorage.setItem("gokz-language", "ru")
    localStorage.setItem("access_token", "translation-test-token")
  })
  await page.route("**/v1/users/me", (route) =>
    route.fulfill({
      json: {
        id: "019d1111-1111-7111-8111-111111111111",
        steamid64: "76561198000000001",
        is_active: true,
        is_superuser: false,
        roles: [],
      },
    }),
  )
  await page.routeWebSocket("**/v1/ws/servers**", () => {})
  await stubMapImageGraphql(page)
  await page.route(/\/v1\/servers\/?(\?.*)?$/, (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 409,
          json: { detail: "Server already exists" },
        })
      : route.fulfill({ json: seedServers }),
  )
  await page.goto("/servers")
  await page.getByTestId("add-server-button").click()
  const dialog = page.getByRole("dialog")
  const add = dialog.getByRole("button", { name: "Добавить", exact: true })
  await add.click()
  await expect(
    dialog.getByText("Укажите адрес сервера", { exact: true }),
  ).toBeVisible()
  await page.getByTestId("add-server-address-input").fill("invalid")
  await add.click()
  await expect(
    dialog.getByText("Используйте формат IP:порт", { exact: true }),
  ).toBeVisible()
  await page.getByTestId("add-server-address-input").fill("10.0.0.1:27015")
  await add.click()
  await expect(
    dialog.getByText("Этот сервер уже есть в списке.", { exact: true }),
  ).toBeVisible()
})

for (const scenario of [
  { name: "standalone", appId: 4465480, direct: true },
  { name: "730", appId: 730, direct: false },
  { name: "unknown", appId: null, direct: false },
  { name: "other", appId: 9032, direct: false },
]) {
  test(`Server connection actions for ${scenario.name} preserve copy command`, async ({
    page,
  }) => {
    const server = {
      ...seedServers.data[0],
      live_status: {
        ...seedServers.data[0].live_status,
        app_id: scenario.appId,
      },
    }
    await stubMapImageGraphql(page)
    await page.routeWebSocket("**/v1/ws/servers**", () => {})
    await page.route(/\/v1\/servers\/?(\?.*)?$/, (route) =>
      route.fulfill({ json: { count: 1, data: [server] } }),
    )
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: async (value: string) => {
            ;(window as any).__copiedCommand = value
          },
        },
      })
    })
    await page.goto("/servers?view=grid")
    const card = page.getByTestId("server-card-10.0.0.1:27015")
    await expect(card).toBeVisible()
    await expect(
      card.getByRole("button", { name: "Connect via Steam" }),
    ).toHaveCount(scenario.direct ? 1 : 0)
    await card.getByRole("button", { name: "Copy server address" }).click()
    await expect
      .poll(() => page.evaluate(() => (window as any).__copiedCommand))
      .toBe("connect 10.0.0.1:27015")
    await page.getByTestId("server-card-map-image-10.0.0.1:27015").click()
    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()
    await expect(
      dialog.getByRole("button", { name: "Connect via Steam" }),
    ).toHaveCount(scenario.direct ? 1 : 0)
    await expect(
      dialog.getByRole("button", { name: "Copy server address" }),
    ).toBeVisible()
    await page.screenshot({
      path: `../.temp/screenshots/server-connect-${scenario.name}.png`,
    })
    await page.keyboard.press("Escape")
    await page.getByRole("button", { name: "Table view", exact: true }).click()
    const row = page.getByRole("row").filter({ hasText: "Alpha Seed" })
    await expect(row).toBeVisible()
    await expect(
      row.getByRole("button", { name: "Connect via Steam" }),
    ).toHaveCount(scenario.direct ? 1 : 0)
    await expect(
      row.getByRole("button", { name: "Copy server address" }),
    ).toBeVisible()
  })
}
