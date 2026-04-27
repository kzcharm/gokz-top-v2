import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

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
        name: "kz_timer",
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
    },
    mode: {
      id: 201,
      name: "kz_simple",
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

  await page.route(/\/v1\/records\/recent(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seededRecentRecords),
    })
  })

  await page.goto("/dashboard/records")

  await expect(page).toHaveURL(/\/dashboard\/records$/)
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible()
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
  await expect(page.getByText("Live Server")).toBeVisible()
  await expect(page.getByText("38.456")).toBeVisible()

  const firstRow = page.locator("tbody tr").first()
  await expect(firstRow).toContainText("Live Runner")
  await expect(firstRow).toContainText("Live Server")
  await expect(firstRow).toContainText("3")
})
