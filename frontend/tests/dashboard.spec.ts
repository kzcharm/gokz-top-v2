import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

test("Dashboard defaults to WR cards with combined NUB and PRO gains", async ({
  page,
}) => {
  const recentWrRequestTypes: string[] = []
  const recentWrRequestOffsets: number[] = []
  const recentWrRequestLimits: number[] = []
  await page.addInitScript(() => {
    const sockets: MockWebSocket[] = []
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
      dispatchMessage(payload: unknown) {
        this.onmessage?.({ data: JSON.stringify(payload) })
      }
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      value: MockWebSocket,
    })
    Object.assign(window, {
      __dispatchRecentWrMessage: (payload: unknown) => {
        for (const socket of sockets) socket.dispatchMessage(payload)
      },
    })
  })

  await page.route(/\/v1\/maps(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ id: 980210, name: "kz_wr_card" }]),
    })
  })
  await page.route(/\/v1\/records\/wrs\/recent(\?.*)?$/, async (route) => {
    const searchParams = new URL(route.request().url()).searchParams
    const requestedType = searchParams.get("type")
    if (requestedType) recentWrRequestTypes.push(requestedType)
    recentWrRequestOffsets.push(Number(searchParams.get("offset") ?? 0))
    recentWrRequestLimits.push(Number(searchParams.get("limit") ?? 0))
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 101,
        data: [
          {
            record: {
              uuid: "019dbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb",
              id: 981020,
              player: {
                steamid64: "76561198000000006",
                name: "WR Runner",
                alias: null,
                avatar_hash: null,
                country: "DE",
              },
              map: { id: 980210, name: "kz_wr_card", tier: 5 },
              server: { id: 980300, name: "WR Server", group: null },
              mode: { id: 200, name: "KZT" },
              stage: 0,
              teleports: 0,
              time: 48.75,
              points: 1000,
              created_on: "2026-09-15T12:00:00Z",
              updated_on: "2026-09-15T12:00:00Z",
              is_replay_available: false,
            },
            achievements: [
              {
                type: "NUB",
                previous_record_uuid: "019daaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa",
                previous_player_name:
                  "Previous Runner With An Extremely Long Display Name",
                previous_time: 50,
                improvement_seconds: 1.25,
              },
              {
                type: "PRO",
                previous_record_uuid: null,
                previous_time: null,
                improvement_seconds: null,
              },
            ],
          },
        ],
      }),
    })
  })

  await page.goto("/dashboard")

  await expect(page).toHaveURL(/\/dashboard\/wrs$/)
  await expect(page.getByRole("tab", { name: "WRs" })).toBeVisible()
  const card = page.getByTestId(
    "recent-wr-card-019dbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb",
  )
  await expect(card).toContainText("kz_wr_card")
  await expect(card).toContainText("WR Runner")
  const imagePlayerName = card.getByTestId("recent-wr-player-name")
  await expect(imagePlayerName).toHaveText("WR Runner")
  await expect(imagePlayerName).toHaveClass(/truncate/)
  const recordSubline = card.getByTestId("player-record-subline")
  await expect(recordSubline).toHaveText("KZT · NUB · 48.750")
  await expect(card.getByText("WR Server", { exact: true })).toHaveCount(0)
  const imageWrTime = card.getByTestId("recent-wr-time")
  await expect(imageWrTime).toHaveText("48.750")
  await expect(imageWrTime).toHaveCSS("font-family", /Arial/)
  await expect(imageWrTime).toHaveClass(/font-normal/)
  await expect(imageWrTime).not.toHaveClass(/-webkit-text-stroke/)
  await expect(card.getByText("World Record", { exact: true })).toHaveCount(0)
  await expect(card).toContainText("-1.250 (prev.")
  const previousPlayerName = card.getByTestId("recent-wr-previous-player")
  await expect(previousPlayerName).toHaveText(
    "Previous Runner With An Extremely Long Display Name",
  )
  await expect(previousPlayerName).toHaveClass(/truncate/)
  await expect(card.getByTestId("recent-wr-type")).toContainText("NUB / PRO WR")
  await expect(card.getByRole("link", { name: "History" })).toHaveCount(0)
  await expect(
    card
      .getByTestId("recent-wr-map-preview")
      .getByTestId("recent-wr-created-at"),
  ).toBeVisible()
  await expect.poll(() => recentWrRequestTypes.at(-1)).toBe("NUB")
  const tierFilter = page.getByRole("combobox", { name: "Tier" })
  await expect(tierFilter).toHaveClass(/min-w-24/)
  const wrTypeToggle = page.getByRole("button", {
    name: "Toggle NUB or PRO WRs",
  })
  await expect(wrTypeToggle).toHaveText("NUB")
  await wrTypeToggle.click()
  await expect(wrTypeToggle).toHaveText("PRO")
  await expect.poll(() => recentWrRequestTypes.at(-1)).toBe("PRO")
  await expect(recordSubline).toContainText("PRO")
  await expect(card).toContainText("First WR")
  await expect(card.getByTestId("recent-wr-type")).toContainText("NUB / PRO WR")
  const mapPreviewBox = await card
    .getByTestId("recent-wr-map-preview")
    .boundingBox()
  expect(mapPreviewBox).not.toBeNull()
  expect(mapPreviewBox!.width / mapPreviewBox!.height).toBeCloseTo(16 / 9, 2)
  await expect.poll(() => recentWrRequestOffsets).toContain(80)
  expect(recentWrRequestOffsets).not.toContain(100)
  expect(recentWrRequestLimits.every((limit) => limit === 20)).toBe(true)
  await expect(page.getByTestId("recent-wrs-load-more")).toHaveCount(0)
  await expect(
    page.getByRole("button", { name: "Go to next page" }),
  ).toHaveCount(0)

  await page.evaluate(() => {
    ;(window as any).__dispatchRecentWrMessage({
      type: "recent_wrs.snapshot",
      count: 21,
      data: [
        {
          record: {
            uuid: "019dcccc-cccc-7ccc-8ccc-cccccccccccc",
            id: 981021,
            player: {
              steamid64: "76561198000000007",
              display_name: "Live WR Runner",
            },
            map: { id: 980210, name: "kz_wr_card", tier: 5 },
            server: { id: 980300, name: "WR Server", group: null },
            mode: { id: 200, name: "KZT" },
            stage: 0,
            teleports: 0,
            time: 47.5,
            points: 1000,
            created_on: "2026-09-15T12:01:00Z",
            updated_on: "2026-09-15T12:01:00Z",
            is_replay_available: false,
          },
          achievements: [
            {
              type: "NUB",
              previous_record_uuid: "019dbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb",
              previous_time: 48.75,
              improvement_seconds: 1.25,
            },
          ],
        },
      ],
    })
  })
  await expect(
    page.getByTestId("recent-wr-player-name").filter({
      hasText: "Live WR Runner",
    }),
  ).toBeVisible()
})

const seededRecentRecords = {
  count: 1,
  data: [
    {
      uuid: "019d5555-5555-7555-8555-555555555555",
      id: 981000,
      player: {
        steamid64: "76561198000000001",
        name: "Seed Runner",
        alias: "Seed Alias",
        avatar_hash: null,
        country: "DE",
      },
      map: {
        id: 980200,
        name: "kz_seed",
        tier: 4,
      },
      server: {
        id: 980300,
        name: "Seed Server",
      },
      mode: {
        id: 200,
        name: "KZT",
      },
      stage: 0,
      teleports: 0,
      time: 42.123,
      points: 350,
      created_on: "2026-03-30T12:00:00Z",
      updated_on: "2026-03-30T12:00:00Z",
    },
  ],
}

const dashboardMaps = [
  { id: 980200, name: "kz_recent_alpha" },
  { id: 980201, name: "kz_recent_beta" },
]

const filterableRecentRecords = [
  {
    uuid: "019d7777-7777-7777-8777-777777777777",
    id: 981010,
    player: {
      steamid64: "76561198000000003",
      name: "Alpha Pro",
      alias: null,
      avatar_hash: null,
      country: "CA",
    },
    map: { id: 980200, name: "kz_recent_alpha", tier: 4 },
    server: { id: 980300, name: "Filter Server" },
    mode: { id: 200, name: "KZT" },
    stage: 0,
    teleports: 0,
    time: 30.111,
    points: 1000,
    created_on: "2026-03-30T12:10:00Z",
    updated_on: "2026-03-30T12:10:00Z",
  },
  {
    uuid: "019d8888-8888-7888-8888-888888888888",
    id: 981011,
    player: {
      steamid64: "76561198000000004",
      name: "Alpha Nub",
      alias: null,
      avatar_hash: null,
      country: "SE",
    },
    map: { id: 980200, name: "kz_recent_alpha", tier: 6 },
    server: { id: 980300, name: "Filter Server" },
    mode: { id: 201, name: "SKZ" },
    stage: 2,
    teleports: 4,
    time: 31.222,
    points: 850,
    created_on: "2026-03-30T12:11:00Z",
    updated_on: "2026-03-30T12:11:00Z",
  },
  {
    uuid: "019d9999-9999-7999-8999-999999999999",
    id: 981012,
    player: {
      steamid64: "76561198000000005",
      name: "Beta Nub",
      alias: null,
      avatar_hash: null,
      country: "US",
    },
    map: { id: 980201, name: "kz_recent_beta", tier: 7 },
    server: { id: 980300, name: "Filter Server" },
    mode: { id: 201, name: "SKZ" },
    stage: 0,
    teleports: 5,
    time: 32.333,
    points: 950,
    created_on: "2026-03-30T12:12:00Z",
    updated_on: "2026-03-30T12:12:00Z",
  },
]

const upsertedRecentRecord = {
  type: "record.upserted",
  record: {
    uuid: "019d6666-6666-7666-8666-666666666666",
    id: 981001,
    player: {
      steamid64: "76561198000000002",
      name: "Live Runner",
      alias: null,
      avatar_hash: null,
      country: "US",
    },
    map: {
      id: 980201,
      name: "kz_live",
      tier: 6,
    },
    server: {
      id: 980301,
      name: "Live Server",
      group: {
        id: "22222222-2222-4222-8222-222222222222",
        name: "Live Server Group",
        custom_id: "live-server-group",
      },
    },
    mode: {
      id: 201,
      name: "SKZ",
    },
    stage: 2,
    teleports: 3,
    time: 38.456,
    points: 510,
    created_on: "2026-03-30T12:05:00Z",
    updated_on: "2026-03-30T12:05:00Z",
  },
}

test("Public dashboard renders recent records and prepends live updates", async ({
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
      __mockRecentRecordSockets: sockets,
      __dispatchRecentRecordMessage: (payload: unknown) => {
        for (const socket of sockets) {
          socket.dispatchMessage(payload)
        }
      },
    })
  })

  await page.route(/\/v1\/maps(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dashboardMaps),
    })
  })

  await page.route(/\/v1\/records\/recent(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seededRecentRecords),
    })
  })

  await page.goto("/dashboard/records")

  await expect(page).toHaveURL(/\/dashboard\/records$/)
  await expect(page.getByRole("tab", { name: "Records" })).toBeVisible()
  await expect(page.getByText("Seed Alias")).toBeVisible()
  await expect(page.getByText("kz_seed")).toBeVisible()
  await expect(page.getByText("Main")).toBeVisible()
  await expect(page.getByText("Seed Server")).toBeVisible()
  await expect(page.getByText("42.123")).toBeVisible()

  await page.waitForFunction(() => {
    return (
      Array.isArray((window as any).__mockRecentRecordSockets) &&
      (window as any).__mockRecentRecordSockets.length > 0
    )
  })

  await page.evaluate((payload) => {
    ;(window as any).__dispatchRecentRecordMessage(payload)
  }, upsertedRecentRecord)

  await expect(page.getByText("Live Runner")).toBeVisible()
  await expect(page.getByText("kz_live")).toBeVisible()
  await expect(page.getByText("Bonus 2")).toBeVisible()
  await expect(
    page.getByRole("link", { name: "Live Server Group" }),
  ).toHaveAttribute("href", "/servers/group/live-server-group")
  await expect(page.getByText("Live Server", { exact: true })).toHaveCount(0)
  await expect(page.getByText("38.456")).toBeVisible()

  const firstRow = page.locator("tbody tr").first()
  await expect(firstRow).toContainText("Live Runner")
  await expect(firstRow).toContainText("Live Server Group")
  await expect(firstRow).toContainText("3")

  await page.getByRole("link", { name: "Live Server Group" }).click()
  await expect(page).toHaveURL(/\/servers\/group\/live-server-group$/)
})

test("Public dashboard sends recent record filters to the backend and guards live updates", async ({
  page,
}) => {
  const recentRequestUrls: string[] = []

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
      __mockRecentRecordSockets: sockets,
      __dispatchRecentRecordMessage: (payload: unknown) => {
        for (const socket of sockets) {
          socket.dispatchMessage(payload)
        }
      },
    })

    window.localStorage.setItem("gokz-app-scope", "SKZ")
  })

  await page.route(/\/v1\/maps(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dashboardMaps),
    })
  })

  await page.route(/\/v1\/records\/recent(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    recentRequestUrls.push(url.toString())
    const rows = filterableRecentRecords.filter((record) => {
      const scope = url.searchParams.get("scope")
      const mapId = url.searchParams.get("map_id")
      const stage = url.searchParams.get("stage")
      const isBonus = url.searchParams.get("is_bonus")
      const tier = url.searchParams.get("tier")
      const type = url.searchParams.get("type")
      const minPoints = url.searchParams.get("points_more_or_equal_than")
      const maxPoints = url.searchParams.get("points_less_or_equal_than")

      if (scope === "SKZ" && record.mode.name !== "SKZ") return false
      if (mapId && record.map.id !== Number(mapId)) return false
      if (stage && record.stage !== Number(stage)) return false
      if (isBonus === "true" && record.stage <= 0) return false
      if (isBonus === "false" && record.stage !== 0) return false
      if (tier && record.map.tier !== Number(tier)) return false
      if (type === "PRO" && record.teleports !== 0) return false
      if (type === "NUB" && record.teleports <= 0) return false
      if (minPoints && record.points < Number(minPoints)) return false
      if (maxPoints && record.points > Number(maxPoints)) return false
      return true
    })

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ count: rows.length, data: rows }),
    })
  })

  await page.goto("/dashboard/records")

  await expect(page.getByText("Alpha Pro")).not.toBeVisible()
  await expect(page.getByText("Alpha Nub")).toBeVisible()
  await expect(page.getByText("Beta Nub")).toBeVisible()
  expect(recentRequestUrls.at(-1)).toContain("scope=SKZ")

  await page.getByRole("combobox", { name: "Choose map" }).fill("beta")
  await page.getByRole("option", { name: "kz_recent_beta" }).click()
  await expect(page.getByText("Beta Nub")).toBeVisible()
  await expect(page.getByText("Alpha Nub")).not.toBeVisible()
  expect(recentRequestUrls.at(-1)).toContain("map_id=980201")

  await page.getByRole("button", { name: "Clear selected map" }).click()
  await page
    .getByRole("combobox", { name: "Filter recent records by stage" })
    .click()
  await page.getByRole("option", { name: "Bonus" }).click()
  await page
    .getByRole("combobox", { name: "Filter recent records by tier" })
    .click()
  await page.getByRole("option", { name: "T6" }).click()
  await page
    .getByRole("combobox", { name: "Filter recent records by NUB or PRO" })
    .click()
  await page.getByRole("option", { name: "NUB", exact: true }).click()
  await page
    .getByRole("combobox", { name: "Filter recent records by points" })
    .click()
  await page.getByRole("option", { name: "800+" }).click()

  await expect(page.getByText("Alpha Nub")).toBeVisible()
  await expect(page.getByText("Alpha Pro")).not.toBeVisible()
  const filteredUrl = recentRequestUrls.at(-1)
  expect(filteredUrl).toContain("scope=SKZ")
  expect(filteredUrl).not.toContain("mode=")
  expect(filteredUrl).toContain("is_bonus=true")
  expect(filteredUrl).toContain("tier=6")
  expect(filteredUrl).toContain("type=NUB")
  expect(filteredUrl).toContain("points_more_or_equal_than=800")
  expect(filteredUrl).not.toContain("points_less_or_equal_than")

  await page
    .getByRole("combobox", { name: "Filter recent records by points" })
    .click()
  await page.getByRole("option", { name: "WR" }).click()
  await expect(
    page.getByText("No recent records match the current filters."),
  ).toBeVisible()

  await page
    .getByRole("combobox", { name: "Filter recent records by points" })
    .click()
  await page.getByRole("option", { name: "800+" }).click()

  await page.evaluate(
    (payload) => {
      ;(window as any).__dispatchRecentRecordMessage(payload)
    },
    {
      type: "record.upserted",
      record: filterableRecentRecords[2],
    },
  )
  await expect(page.getByText("Beta Nub")).not.toBeVisible()

  await page.evaluate(
    (payload) => {
      ;(window as any).__dispatchRecentRecordMessage(payload)
    },
    {
      type: "record.upserted",
      record: {
        ...filterableRecentRecords[1],
        uuid: "019daaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa",
        id: 981013,
        player: {
          ...filterableRecentRecords[1].player,
          name: "Live Filter Match",
        },
        created_on: "2026-03-30T12:13:00Z",
        updated_on: "2026-03-30T12:13:00Z",
      },
    },
  )
  await expect(page.getByText("Live Filter Match")).toBeVisible()
})
