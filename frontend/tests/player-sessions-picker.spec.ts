import { expect, test } from "@playwright/test"
import { stubBackgroundApi } from "./utils/backgroundApi"

test.use({ storageState: { cookies: [], origins: [] } })

const player = {
  steamid64: "76561198012345678",
  name: "Session Runner",
  displayName: "Session Runner",
  alias: null,
  country: "DE",
  primaryScope: "OVR",
  rating: 0,
  roles: null,
}

test.beforeEach(async ({ page }) => {
  await stubBackgroundApi(page)
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "mock-session")
  })
  await page.route("**/v1/users/me", (route) =>
    route.fulfill({ json: { ...player, roles: ["superuser"], player } }),
  )
  await page.route("**/v1/admin/servers/groups", (route) =>
    route.fulfill({ json: { data: [], count: 0 } }),
  )
  await page.route(/\/v1\/admin\/player-sessions(\?.*)?$/, (route) =>
    route.fulfill({ json: { data: [], count: 0 } }),
  )
  await page.route("**/v1/graphql", (route) =>
    route.fulfill({
      json: {
        data: { searchPlayers: { data: [player], count: 1 }, players: [] },
      },
    }),
  )
})

test("player picker stays above the sessions header and selects and clears the filter", async ({
  page,
}) => {
  await page.goto("/admin/player-sessions")
  await page.getByLabel("Filter sessions by player").fill("Session")
  const result = page.getByRole("button", { name: /Session Runner/ })
  await expect(result).toBeVisible()
  const header = page.getByRole("columnheader", { name: "Player", exact: true })
  await expect
    .poll(async () => {
      const headerBox = await header.boundingBox()
      if (!headerBox) return false
      return result.evaluate((button, box) => {
        const rect = button.getBoundingClientRect()
        const y = Math.max(rect.top, box.y) + 2
        return (
          y < Math.min(rect.bottom, box.y + box.height) &&
          button.contains(document.elementFromPoint(rect.x + rect.width / 2, y))
        )
      }, headerBox)
    })
    .toBe(true)

  const filtered = page.waitForRequest((request) =>
    request.url().includes(`player_steamid64=${player.steamid64}`),
  )
  await result.click()
  await filtered
  await expect(page.getByLabel("Filter sessions by player")).toHaveValue(
    player.name,
  )
  const cleared = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return (
      url.pathname === "/v1/admin/player-sessions" &&
      !url.searchParams.has("player_steamid64")
    )
  })
  await page
    .getByRole("button", { name: "Clear selected player filter" })
    .click()
  await cleared
  await expect(page.getByLabel("Filter sessions by player")).toHaveValue("")
})

test("Find Alts immediately looks up the selected sessions filter player", async ({
  page,
}) => {
  const requestedPlayers: string[] = []
  await page.route("**/v1/admin/player-sessions/ip-links**", (route) => {
    requestedPlayers.push(
      new URL(route.request().url()).searchParams.get("steamid64") ?? "",
    )
    return route.fulfill({
      json: { players: [], links: [], skipped_buckets: [] },
    })
  })
  await page.goto("/admin/player-sessions")
  await page.getByLabel("Filter sessions by player").fill("Session")
  await page.getByRole("button", { name: /Session Runner/ }).click()
  await page.getByRole("button", { name: "Find Alts", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog.getByLabel("Search player for alt lookup")).toHaveValue(
    player.name,
  )
  await expect.poll(() => requestedPlayers).toEqual([player.steamid64])
  await expect(
    dialog.getByText("Linked players", { exact: true }),
  ).toBeVisible()
})

test("alt lookup supports picked players and direct SteamID64 entry", async ({
  page,
}) => {
  const requestedPlayers: string[] = []
  await page.route("**/v1/admin/player-sessions/ip-links**", (route) => {
    requestedPlayers.push(
      new URL(route.request().url()).searchParams.get("steamid64") ?? "",
    )
    return route.fulfill({
      json: { players: [], links: [], skipped_buckets: [] },
    })
  })
  await page.goto("/admin/player-sessions")
  await page.getByRole("button", { name: "Find Alts", exact: true }).click()
  const dialog = page.getByRole("dialog")
  const input = dialog.getByLabel("Search player for alt lookup")
  await input.fill("Session")
  await expect(
    dialog.getByRole("button", { name: /Session Runner/ }),
  ).toBeVisible()
  await input.press("Enter")
  await expect(input).toHaveValue(player.name)
  await dialog.getByRole("button", { name: "Find Alts", exact: true }).click()
  await expect.poll(() => requestedPlayers).toEqual([player.steamid64])
  await expect(
    dialog.getByText("Linked players", { exact: true }),
  ).toBeVisible()
  await dialog
    .getByRole("button", { name: "Clear selected player", exact: true })
    .click()
  await expect(dialog.getByText("Linked players", { exact: true })).toHaveCount(
    0,
  )
  await expect(
    dialog.getByRole("button", { name: "Find Alts", exact: true }),
  ).toBeDisabled()

  await page.route("**/v1/graphql", (route) =>
    route.fulfill({
      json: { data: { searchPlayers: { data: [], count: 0 } } },
    }),
  )
  await input.fill("76561198000000042")
  await expect(dialog.getByText("No players found.")).toBeVisible()
  await input.press("Enter")
  await expect
    .poll(() => requestedPlayers)
    .toEqual([player.steamid64, "76561198000000042"])
})

test("alt links display players in From and To without the dialog description", async ({
  page,
}) => {
  const linkedPlayer = {
    ...player,
    steamid64: "76561198000000042",
    name: "Linked Runner",
    displayName: "Linked Runner",
  }
  await page.route("**/v1/admin/player-sessions/ip-links**", (route) =>
    route.fulfill({
      json: {
        players: [
          { player, distance: 0, link_count: 1 },
          { player: linkedPlayer, distance: 1, link_count: 1 },
        ],
        links: [
          {
            from_steamid64: player.steamid64,
            to_steamid64: linkedPlayer.steamid64,
            bucket: { key: "192.0.2.42", label: "192.0.2.42" },
            session_count_from: 1,
            session_count_to: 1,
            first_seen_at: "2026-11-01T12:00:00Z",
            last_seen_at: "2026-11-02T12:00:00Z",
          },
        ],
        skipped_buckets: [],
      },
    }),
  )
  await page.goto("/admin/player-sessions")
  await page.getByRole("button", { name: "Find Alts", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await expect(
    dialog.getByText("Search player sessions by shared IP evidence."),
  ).toHaveCount(0)
  await dialog.getByLabel("Search player for alt lookup").fill("Session")
  await dialog.getByRole("button", { name: /Session Runner/ }).click()
  await dialog.getByRole("button", { name: "Find Alts", exact: true }).click()
  await expect(
    dialog.locator("details").filter({ hasText: "Links (1)" }),
  ).toHaveAttribute("open", "")
  const row = dialog.getByRole("row").filter({ hasText: "192.0.2.42" })
  await expect(
    row
      .getByRole("cell")
      .nth(0)
      .getByRole("link", { name: /Session Runner/ }),
  ).toBeVisible()
  await expect(
    row
      .getByRole("cell")
      .nth(1)
      .getByRole("link", { name: /Linked Runner/ }),
  ).toBeVisible()
})
