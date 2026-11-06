import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

test("browser rooms and map menu launch Web GOKZ without exposing credentials", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.route("**/v1/**", (route) =>
    route.fulfill({ json: { data: [], count: 0 } }),
  )
  await page.route("**/v1/maps?*", (route) => route.fulfill({ json: [] }))
  const server = (id: number, web: boolean) => ({
    id: `server-${id}`,
    ip: web ? "web-gokz" : "203.0.113.1",
    port: web ? id : 27015,
    status: "enabled",
    is_public: true,
    country: "DE",
    map_tier: 4,
    created_at: "2026-11-06T12:00:00Z",
    updated_at: "2026-11-06T12:00:00Z",
    source: web ? { type: "web_gokz", room_id: id } : { type: "manual" },
    group_id: web ? "web-group" : "axe-group",
    group: {
      id: web ? "web-group" : "axe-group",
      name: web ? "Web GOKZ" : "AXE GOKZ",
      custom_id: web ? "web-gokz" : "axe-gokz",
    },
    live_status: {
      hostname: web ? `Web GOKZ #${id}` : "AXE server",
      map: "kz_ominous2",
      player_count: id === 2 || id === 3 ? 1 : 0,
      max_players: 16,
      players:
        id === 2 || id === 3
          ? [
              {
                steamid64: "76561198000000001",
                name: "Card Runner",
                mode: "NKZ",
                timer_time: 12.5,
              },
            ]
          : [],
      is_online: true,
    },
  })
  await page.route("**/v1/servers?*", (route) =>
    route.fulfill({
      json: {
        data: [
          server(3, false),
          {
            ...server(4, false),
            ip: "203.0.113.2",
            group_id: null,
            group: null,
          },
        ],
        count: 2,
      },
    }),
  )
  await page.routeWebSocket("**/v1/ws/servers", () => {})
  await page.route("**/v1/web-gokz/servers", (route) =>
    route.fulfill({
      json: {
        data: [1, 2].map((id) => server(id, true)),
        count: 2,
      },
    }),
  )
  await page.goto("/servers")
  const first = page.getByTestId("server-card-web-gokz:1")
  await expect(first).toBeVisible()
  await expect(page.getByTestId("server-card-web-gokz:2")).toBeVisible()
  const groups = page.getByRole("button", {
    name: /^(Web GOKZ|AXE GOKZ|Others)\s*\(\d+\)$/,
  })
  await expect(groups).toHaveText(["AXE GOKZ(1)", "Others(0)", "Web GOKZ(1)"])
  await expect(first.getByText("T4", { exact: true })).toBeVisible()
  await expect(first.getByText("Browser play", { exact: true })).toHaveCount(0)
  await expect(first.getByRole("img", { name: "Germany" })).toHaveCount(0)
  await expect(first.getByRole("button", { name: /copy/i })).toHaveCount(0)
  const native = page.getByTestId("server-card-203.0.113.1:27015")
  await expect(native.getByRole("img", { name: "Germany" })).toBeVisible()
  await expect(native.getByRole("button", { name: /copy/i })).toBeVisible()
  const occupied = page.getByTestId("server-card-web-gokz:2")
  for (const card of [native, occupied]) {
    const player = card.getByRole("link", { name: /Card Runner/ })
    await expect(player).toContainText("[NKZ]Card Runner")
    await expect(player).toHaveCSS("font-size", "12px")
    await expect(player.locator('[data-slot="avatar"]')).toHaveCSS(
      "width",
      "16px",
    )
  }
  for (const card of [first, occupied]) {
    const gap = await card.evaluate(
      (element) =>
        element.getBoundingClientRect().bottom -
        element.lastElementChild!.getBoundingClientRect().bottom,
    )
    expect(gap).toBeLessThanOrEqual(1)
    await expect(card.locator(":scope > div").last()).toHaveClass(
      /bg-primary\/10/,
    )
  }
  await page.route("**/web-gokz/connect?launch=1&room=1", (route) =>
    route.fulfill({ contentType: "text/html", body: "Launch" }),
  )
  const popupPromise = page.waitForEvent("popup")
  await first
    .getByRole("button", { name: "Play in browser", exact: true })
    .click()
  const popup = await popupPromise
  await expect(popup).toHaveURL(
    "http://localhost:5173/web-gokz/connect?launch=1&room=1",
  )
  await popup.close()
  await first
    .getByRole("link", { name: "kz_ominous2" })
    .first()
    .click({ button: "right" })
  await expect(
    page.getByRole("menuitem", { name: "Play in browser" }),
  ).toHaveAttribute(
    "href",
    "http://localhost:5173/web-gokz/connect?launch=1&map=kz_ominous2",
  )
})

test("login handoff sends only the scoped session to the configured game origin", async ({
  page,
  context,
}) => {
  await context.addInitScript(() =>
    localStorage.setItem("access_token", "website-secret"),
  )
  await context.route("**/v1/**", (route) =>
    route.fulfill({ json: { data: [], count: 0 } }),
  )
  await context.route("**/v1/web-gokz/session", async (route) => {
    expect(route.request().headers().authorization).toBe(
      "Bearer website-secret",
    )
    await route.fulfill({
      json: {
        access_token: "game-scoped-token",
        player: { steamid64: "76561198000000001", name: "Player" },
      },
    })
  })
  await context.route("http://localhost:5180/**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: '<button onclick="window.open(\'http://localhost:5173/web-gokz/connect?origin=https://attacker.example\')">Connect</button><script>window.addEventListener("message",event=>{document.body.dataset.session=JSON.stringify(event.data)})</script>',
    }),
  )
  await page.goto("http://localhost:5180/")
  await page.getByRole("button", { name: "Connect" }).click()
  await expect(page.locator("body")).toHaveAttribute(
    "data-session",
    /game-scoped-token/,
    { timeout: 15000 },
  )
  const received = await page.locator("body").getAttribute("data-session")
  expect(received).not.toContain("website-secret")
})

test("website play authenticates through a one-time code without a second sign-in click", async ({
  page,
  context,
}) => {
  await context.addInitScript(() =>
    localStorage.setItem("access_token", "website-secret"),
  )
  await context.route("**/v1/**", (route) =>
    route.fulfill({ json: { data: [], count: 0 } }),
  )
  await context.route("**/v1/web-gokz/launch", (route) => {
    expect(route.request().headers().authorization).toBe(
      "Bearer website-secret",
    )
    return route.fulfill({ json: { code: "short-lived-code", expires_in: 60 } })
  })
  await context.route("http://localhost:5180/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "Game" }),
  )
  await page.goto(
    "/web-gokz/connect?launch=1&map=kz_ominous2&origin=https://attacker.example",
  )
  await expect(page).toHaveURL(
    "http://localhost:5180/practice?map=kz_ominous2#login_code=short-lived-code",
  )
  expect(page.url()).not.toContain("website-secret")
})

test("anonymous solo play remains available without signing in", async ({
  page,
  context,
}) => {
  await context.addInitScript(() => localStorage.removeItem("access_token"))
  await context.route("**/v1/**", (route) =>
    route.fulfill({ json: { data: [], count: 0 } }),
  )
  await context.route("http://localhost:5180/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "Solo game" }),
  )
  await page.goto("/web-gokz/connect?launch=1&map=kz_ominous2")
  await expect(page).toHaveURL("http://localhost:5180/practice?map=kz_ominous2")
})
