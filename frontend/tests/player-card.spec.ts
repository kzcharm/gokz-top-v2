import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const steamid64 = "76561198000000001"
const skills = Object.fromEntries(
  ["boxtech", "strafe", "bhop", "climb", "ladder", "slide"].map(
    (key, index) => [key, { raw_rating: 100, rating: 5 + index * 0.7 }],
  ),
)
async function mockCard(
  page: Page,
  options: {
    empty?: boolean
    error?: boolean
    longName?: boolean
    partial?: boolean
    slow?: boolean
    largePoints?: boolean
    brokenAvatar?: boolean
  } = {},
) {
  const requests: string[] = []
  page.on("websocket", (socket) => {
    if (socket.url().includes("/v1/")) requests.push("websocket")
  })
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url())
    requests.push(`${route.request().method()} ${url.pathname}`)
    let body: unknown = []
    if (
      [
        `/v1/players/${steamid64}`,
        "/v1/players/saki",
        "/v1/players/sak",
      ].includes(url.pathname)
    ) {
      expect(url.searchParams.get("refresh_steam_profile")).toBe("false")
      if (options.error || url.pathname.endsWith("/sak"))
        return route.fulfill({
          status: 404,
          json: { detail: "Player not found" },
        })
      body = {
        steamid64,
        name: options.longName
          ? "A very long player name that wraps onto two readable lines"
          : "Saki",
        alias: null,
        country: "DE",
        avatar_hash: options.brokenAvatar ? "broken" : null,
        custom_id: "saki",
        created_at: "2022-01-01T00:00:00Z",
        last_played_at: "2026-08-01T00:00:00Z",
        favorite_server: options.empty ? null : { label: "AXE GOKZ" },
      }
    } else if (url.pathname === "/v1/maps") {
      body = Array.from({ length: 8 }, (_, index) => ({
        id: index + 1,
        name: `kz_map_${index}`,
        tiers: {
          OVR: index + 1,
          KZT: index + 1,
          SKZ: index + 1,
          VNL: index + 1,
        },
      }))
    } else if (url.pathname.endsWith("/stats")) {
      expect(url.searchParams.get("type")).toBe("playtime")
      body = { playtime: { total_seconds: options.empty ? 0 : 2645280 } }
    } else if (url.pathname.endsWith("/jumpstats")) {
      body = {
        data: options.empty ? [] : [{ distance: 275.79 }],
        count: options.empty ? 0 : 1,
      }
    } else if (url.pathname === "/v1/records/pb") {
      if (options.slow) await new Promise((resolve) => setTimeout(resolve, 500))
      body = options.empty
        ? []
        : url.searchParams.get("type") === "PRO"
          ? [{ map_id: 1, points: options.largePoints ? 123456789 : 500 }]
          : [
              { map_id: 1, points: 1000 },
              { map_id: 2, points: 950 },
              { map_id: 3, points: 850 },
            ]
    } else if (url.pathname.startsWith("/v1/leaderboards/players/")) {
      body = options.empty
        ? { rating: null, rank: null, skill_ratings: null }
        : {
            rating: 7.52,
            rank: 42,
            rank_regional: 12,
            region: "EU",
            skill_ratings: options.partial
              ? { ...skills, ladder: { rating: null } }
              : skills,
          }
    } else throw new Error(`Unexpected request: ${url.pathname}`)
    return route.fulfill({ json: body })
  })
  return requests
}
for (const lang of ["en", "zh-CN", "ru"]) {
  for (const width of [360, 480]) {
    test(`${lang} at ${width}px`, async ({ page }) => {
      const requests = await mockCard(page, { longName: width === 360 })
      await page.setViewportSize({ width, height: 1200 })
      await page.goto(`/cards/player/${steamid64}?scope=KZT&lang=${lang}`)
      const card = page.getByTestId("player-card")
      await expect(card).toHaveAttribute("data-render-state", "ready")
      await expect(card).toContainText("3,300")
      await expect(card).toContainText("3 / 8")
      await expect(card).toContainText("#42")
      await expect(card).toContainText("#12")
      await expect(card.locator("header .card-radar svg")).toHaveCount(1)
      const radarLabelsFit = await card
        .locator(".card-radar svg")
        .evaluate((element) => {
          const svg = element as SVGSVGElement
          const view = svg.viewBox.baseVal
          return Array.from(svg.querySelectorAll("text")).every((label) => {
            const box = label.getBBox()
            return box.y >= view.y && box.y + box.height <= view.y + view.height
          })
        })
      expect(radarLabelsFit).toBeTruthy()

      await expect(card.locator("header .card-summary")).toContainText("#42")
      await expect(card).not.toContainText("AXE GOKZ")
      await expect(card).toContainText(lang === "ru" ? "275,79" : "275.79")
      await expect(card).not.toContainText("相对技能优势")
      await expect(card).not.toContainText("技能雷达")
      if (lang === "zh-CN") {
        await expect(card).toContainText("路线")
        await expect(card).toContainText("攀岩")
      }
      await expect(card.locator('[aria-label="Germany"]')).toHaveCount(1)
      await expect(card).not.toContainText(steamid64)
      await expect(card).not.toContainText(/gokz\.top/i)
      await expect(card.locator("a, button")).toHaveCount(0)
      await expect(
        card.locator('[data-testid="profile-skill-radar-polygon"]'),
      ).toHaveCount(1)
      expect(
        requests.every((request) => request.startsWith("GET ")),
      ).toBeTruthy()
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(width)
      await card.screenshot({
        path: `../.temp/player-card/${lang}-${width}.png`,
      })
    })
  }
}
for (const scope of ["OVR", "KZT", "SKZ", "VNL"]) {
  test(`empty ${scope} profile`, async ({ page }) => {
    await mockCard(page, { empty: true })
    await page.goto(`/cards/player/${steamid64}?scope=${scope}`)
    const card = page.getByTestId("player-card")
    await expect(card).toHaveAttribute("data-render-state", "ready")
    await expect(card).toHaveAttribute("data-scope", scope)
    await expect(card).toContainText("Unranked")
    await expect(card).toContainText("0 / 8")
    await expect(
      card.locator('[data-testid="profile-skill-radar-polygon"]'),
    ).toHaveCount(0)
  })
}
test("unknown player signals an error", async ({ page }) => {
  await mockCard(page, { error: true })
  await page.goto(`/cards/player/${steamid64}`)
  await expect(page.getByTestId("player-card")).toHaveAttribute(
    "data-render-state",
    "error",
  )
})
test("waits for data and preserves missing skill values", async ({ page }) => {
  await mockCard(page, { partial: true, slow: true })
  await page.goto(`/cards/player/${steamid64}`)
  await expect(page.getByTestId("player-card")).toHaveAttribute(
    "data-render-state",
    "loading",
  )
  await expect(page.getByTestId("player-card")).toHaveAttribute(
    "data-render-state",
    "ready",
  )
  await expect(page.locator('[data-skill-label="ladder"]')).toContainText("—")
})

test("failed avatar falls back and slow assets delay readiness", async ({
  page,
}) => {
  await mockCard(page, { brokenAvatar: true })
  await page.route("https://avatars.steamstatic.com/**", (route) =>
    route.abort(),
  )
  await page.route("**/*trophy*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200))
    await route.continue()
  })
  await page.goto(`/cards/player/${steamid64}`)
  await expect(page.getByTestId("player-card")).toHaveAttribute(
    "data-render-state",
    "ready",
  )
  await expect(
    page.getByTestId("player-card").locator("img").first(),
  ).not.toHaveAttribute("src", /steamstatic/)
})

test("custom IDs use the read-only profile option", async ({ page }) => {
  const requests = await mockCard(page)
  await page.goto("/cards/player/saki")
  await expect(page.getByTestId("player-card")).toHaveAttribute(
    "data-render-state",
    "ready",
  )
  expect(requests).toContain("GET /v1/players/saki")
})
test("a fuzzy name match is not accepted as an identifier", async ({
  page,
}) => {
  await mockCard(page)
  await page.goto("/cards/player/sak")
  await expect(page.getByTestId("player-card")).toHaveAttribute(
    "data-render-state",
    "error",
  )
})

test("large points extend right and radar values are larger than labels", async ({
  page,
}) => {
  await mockCard(page, { largePoints: true })
  await page.goto(`/cards/player/${steamid64}?scope=OVR&lang=zh-CN`)
  const card = page.getByTestId("player-card")
  await expect(card).toHaveAttribute("data-render-state", "ready")
  const points = card.locator(".card-points")
  await expect(points).toContainText("123,459,589")
  const metrics = await points.evaluate((el) => {
    const value = el.lastElementChild!
    const range = document.createRange()
    range.selectNodeContents(value)
    return {
      right: range.getBoundingClientRect().right,
      cardRight: el.closest("main")!.getBoundingClientRect().right,
      previous: el.previousElementSibling!.textContent,
    }
  })
  expect(metrics.previous).toContain("LJ PB")
  expect(metrics.right).toBeLessThan(metrics.cardRight)
  const sizes = await card
    .locator('[data-skill-label="slide"] tspan')
    .evaluateAll((spans) =>
      spans.map((span) => parseFloat(getComputedStyle(span).fontSize)),
    )
  expect(sizes[1]).toBeGreaterThan(sizes[0])
})
