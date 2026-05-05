import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

function buildBan(index: number) {
  return {
    id: index,
    ban_type: "cheating",
    created_on: "2026-03-01T12:00:00Z",
    expires_on: null,
    notes: `Ban note ${index}`,
    player: {
      steamid64: `765611980000${index.toString().padStart(5, "0")}`,
      display_name: `Banned Player ${index}`,
    },
    stats: null,
  }
}

test("Bans table supports WASD pagination shortcuts without affecting typing", async ({
  page,
}) => {
  const banRequests: Array<{ offset: string | null; limit: string | null }> = []

  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem("gokz-datetime-format", "iso")
  })

  await page.route("**/v1/bans*", async (route) => {
    const url = new URL(route.request().url())
    const offset = Number(url.searchParams.get("offset") ?? "0")
    const limit = Number(url.searchParams.get("limit") ?? "20")
    banRequests.push({
      offset: url.searchParams.get("offset"),
      limit: url.searchParams.get("limit"),
    })

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: 45,
        data: Array.from({ length: Math.min(limit, 45 - offset) }, (_, index) =>
          buildBan(offset + index + 1),
        ),
      }),
    })
  })

  await page.route("**/v1/graphql", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          searchPlayers: {
            count: 0,
            data: [],
          },
        },
      }),
    })
  })

  await page.goto("/bans")

  await expect(page.getByText("Banned Player 1", { exact: true })).toBeVisible()
  await expect
    .poll(() => banRequests.at(-1))
    .toEqual({ offset: "0", limit: "20" })

  await page.keyboard.press("KeyD")
  await expect(
    page.getByText("Banned Player 21", { exact: true }),
  ).toBeVisible()
  await expect
    .poll(() => banRequests.at(-1))
    .toEqual({ offset: "20", limit: "20" })

  const searchBox = page.getByRole("textbox", { name: "Search players" })
  await searchBox.focus()
  await page.keyboard.press("KeyA")
  await expect(searchBox).toHaveValue("a")
  await expect(
    page.getByText("Banned Player 21", { exact: true }),
  ).toBeVisible()
  await expect
    .poll(() => banRequests.at(-1))
    .toEqual({ offset: "20", limit: "20" })

  await searchBox.fill("")
  await searchBox.evaluate((element) => {
    element.blur()
  })

  await page.keyboard.press("KeyA")
  await expect(page.getByText("Banned Player 1", { exact: true })).toBeVisible()
})
