import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

test("admin social accounts show cached names or plain IDs without overlapping dates", async ({
  page,
}) => {
  const accounts = [
    [
      "youtube",
      "channel/UCca6Cm_Jjucr4CiTgB2d5Bw",
      "Verified Channel With A Very Long Platform Account Name",
    ],
    ["youtube", "@greenvn1", "@greenvn1"],
    ["youtube", "user/LegacyCreator", null],
    ["bilibili", "3546950448187411", "从雨"],
    ["discord", "1010306468047761500", "Cinyan10"],
    ["discord", "664487959650762783", null],
    ["twitch", "chilldooog", "ChillDooog"],
    ["github", "example", "example"],
    ["x", "example_x", "example_x"],
  ]
  await page.addInitScript(() =>
    localStorage.setItem("access_token", "test-token"),
  )
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = { data: [], count: 0 }
    if (path === "/v1/users/me") {
      body = {
        steamid64: "76561198000000001",
        roles: ["superuser"],
        is_active: true,
      }
    } else if (path === "/v1/admin/player-social-links") {
      body = {
        count: accounts.length,
        data: accounts.map(([platform, identifier, name], index) => ({
          id: `link-${index}`,
          player_steamid64: "76561198000000001",
          player: {
            steamid64: "76561198000000001",
            display_name: "Test Player",
          },
          platform,
          account_identifier: identifier,
          account_name: name,
          url: `https://example.com/${identifier}`,
          verified: false,
          created_at: "2026-11-05T15:01:00Z",
        })),
      }
    } else if (path === "/v1/graphql") {
      body = { data: { players: [] } }
    }
    await route.fulfill({ json: body })
  })
  await page.goto("/admin/player-social-links")
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 })
    for (const [, identifier, label] of accounts) {
      const link = page.locator(`a[href="https://example.com/${identifier}"]`)
      await expect(link).toHaveText(label || identifier!)
      await expect(link).toHaveAttribute("title", label || identifier!)
      await expect(link).toHaveAttribute(
        "href",
        `https://example.com/${identifier}`,
      )
      await expect(link).toHaveCSS("text-overflow", "ellipsis")
      const contained = await link.evaluate((element) => {
        const cell = element.closest("td")!
        const dateCell = cell.nextElementSibling!
        const bounds = element.getBoundingClientRect()
        return bounds.right <= dateCell.getBoundingClientRect().left
      })
      expect(contained).toBe(true)
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.screenshot({
    path: "../.temp/screenshots/admin-player-social-links.png",
    fullPage: true,
  })
})
