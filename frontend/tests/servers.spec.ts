import { readFile } from "node:fs/promises"
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
  await page.getByTestId("server-card-10.0.0.3:27017").click()

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
