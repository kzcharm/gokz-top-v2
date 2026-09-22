import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const releasesPayload = [
  {
    id: 2,
    tag_name: "v1.11.1",
    name: "v1.11.1",
    html_url: "https://github.com/kzcharm/gokz-top-v2/releases/tag/v1.11.1",
    published_at: "2026-06-17T15:12:42Z",
    body: [
      "## Features",
      "- feat(maps): improve /maps/:mapName reviews",
      "- feat(profile): show rank on /profile/:identifier",
      "",
      "## Fixes",
      "- fix(records): highlight current pb on /leaderboards",
      "",
      "## Other",
      "- chore(frontend): document production api url",
    ].join("\n"),
    reactions: {
      groups: [
        {
          emoji: {
            key: "unicode:thumbs_up",
            name: "Thumbs up",
            value: "👍",
            image_url: null,
          },
          count: 2,
          reacted_by_me: false,
          reaction_id: null,
        },
      ],
    },
  },
  {
    id: 1,
    tag_name: "v1.11.0",
    name: "v1.11.0",
    html_url: "https://github.com/kzcharm/gokz-top-v2/releases/tag/v1.11.0",
    published_at: "2026-06-17T15:09:00Z",
    body: "## Features\n\n## Fixes\n\n## Other\n",
    reactions: { groups: [] },
  },
]

async function mockUpdatesDependencies(page: Page) {
  await page.route(/\/v1\/reactions\/emojis$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          key: "unicode:thumbs_up",
          name: "Thumbs up",
          value: "👍",
          image_url: null,
        },
        {
          key: "unicode:fire",
          name: "Fire",
          value: "🔥",
          image_url: null,
        },
      ]),
    })
  })
  await page.route(/\/v1\/reactions\/release\/2\/reactors.*/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          {
            player: {
              steamid64: "76561198000000002",
              display_name: "Reaction Player",
              avatar_hash: "abc123",
            },
            created_at: "2026-09-22T12:00:00Z",
          },
        ],
        count: 1,
      }),
    })
  })
  await page.route(/\/v1\/releases(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: releasesPayload }),
    })
  })
  await page.route(/\/v1\/maps(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 1,
          name: "kz_beginnerblock_go",
          filesize: 123,
          validated: true,
          tiers: { OVR: 1, KZT: 1, SKZ: 0, VNL: 0 },
          created_on: "2026-01-01T00:00:00Z",
          updated_on: "2026-01-01T00:00:00Z",
          approved_by_steamid64: "76561198000000001",
          synced_at: "2026-01-01T00:00:00Z",
          workshop_url: null,
        },
      ]),
    })
  })
  await page.route(/\/v1\/leaderboards\/players(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          {
            rank: 1,
            global_rank: 1,
            player: {
              steamid64: "76561198000000001",
              name: "Top Player",
              alias: null,
              avatar_hash: null,
              country: "DE",
              custom_id: "top-player",
              roles: null,
            },
            rating: 1000,
            raw_rating: 1000,
            rating_easy: 500,
            rating_hard: 500,
            points: 1000,
            wrs_nub: 0,
            wrs_pro: 0,
            records_900_plus: 0,
            records_800_plus: 0,
            unique_map_finishes: 10,
          },
        ],
        count: 1,
      }),
    })
  })
}

test("Updates page shows release notes from the cached releases API", async ({
  page,
}) => {
  await mockUpdatesDependencies(page)

  await page.goto("/updates")

  await expect(page.getByRole("heading", { name: "Updates" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "v1.11.1" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "v1.11.0" })).toBeVisible()
  await expect(page.getByText("Features", { exact: true })).toBeVisible()
  await expect(page.getByText("Fixes", { exact: true })).toBeVisible()
  await expect(page.getByText("Other", { exact: true })).toBeVisible()
  await expect(page.getByText("feat(maps): improve")).toBeVisible()
  await expect(
    page.getByRole("link", { name: "/maps/:mapName" }),
  ).toHaveAttribute("href", "/maps/kz_beginnerblock_go")
  await expect(
    page.getByRole("link", { name: "/profile/:identifier" }),
  ).toHaveAttribute("href", "/profile/76561198000000001")
  await expect(
    page.getByRole("link", { name: "/leaderboards" }),
  ).toHaveAttribute("href", "/leaderboards")
  await expect(
    page.getByText("fix(records): highlight current pb on"),
  ).toBeVisible()
  await expect(
    page.getByText("chore(frontend): document production api url"),
  ).toBeVisible()
  await expect(page.getByRole("link", { name: "v1.11.1" })).toHaveAttribute(
    "href",
    "https://github.com/kzcharm/gokz-top-v2/releases/tag/v1.11.1",
  )
  await expect(page.getByRole("link", { name: "View on GitHub" })).toHaveCount(
    0,
  )
  await expect(
    page
      .locator("article")
      .filter({ hasText: "v1.11.0" })
      .getByText("Features", { exact: true }),
  ).toHaveCount(0)
  await expect(
    page
      .locator("article")
      .filter({ hasText: "v1.11.0" })
      .getByText("No release notes were provided for this version."),
  ).toBeVisible()
})

test("Version label opens the updates page without a sidebar item", async ({
  page,
}) => {
  await mockUpdatesDependencies(page)
  await page.goto("/updates?from=version-test")

  const sidebarMenu = page.locator('[data-sidebar="content"]')
  await expect(sidebarMenu.getByRole("link", { name: "Updates" })).toHaveCount(
    0,
  )

  await page.getByRole("button", { name: "Open Sidebar" }).click()
  await page.getByRole("link", { name: "Open release notes" }).click()

  await expect(page).toHaveURL(/\/updates$/)
  await expect(page.getByRole("heading", { name: "Updates" })).toBeVisible()
})

test("release reactions show their public reactor list", async ({ page }) => {
  await mockUpdatesDependencies(page)
  await page.goto("/updates")

  const release = page.locator("article").filter({ hasText: "v1.11.1" })
  await release
    .getByRole("button", { name: "Toggle Thumbs up reaction" })
    .click({ button: "right" })
  await expect(page.getByTestId("reaction-reactor-avatars")).toBeVisible()
  const reactor = page.getByRole("link", { name: "Reaction Player" })
  await expect(reactor).toBeVisible()
  await expect(reactor).toHaveAttribute("href", "/profile/76561198000000002")
})

test("release reactions reveal reactors after a sustained hover", async ({
  page,
}) => {
  await mockUpdatesDependencies(page)
  await page.goto("/updates")

  const release = page.locator("article").filter({ hasText: "v1.11.1" })
  await release
    .getByRole("button", { name: "Toggle Thumbs up reaction" })
    .hover()

  await expect(page.getByTestId("reaction-reactor-avatars")).toBeVisible()
})
