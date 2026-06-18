import { expect, test } from "@playwright/test"

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
      "- feat(records): add run history",
      "",
      "## Fixes",
      "- fix(records): highlight current pb",
      "",
      "## Other",
      "- chore(frontend): document production api url",
    ].join("\n"),
  },
  {
    id: 1,
    tag_name: "v1.11.0",
    name: "v1.11.0",
    html_url: "https://github.com/kzcharm/gokz-top-v2/releases/tag/v1.11.0",
    published_at: "2026-06-17T15:09:00Z",
    body: "## Features\n\n## Fixes\n\n## Other\n",
  },
]

test("Updates page shows release notes from GitHub releases", async ({
  page,
}) => {
  await page.route(
    "https://api.github.com/repos/kzcharm/gokz-top-v2/releases?per_page=20",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(releasesPayload),
      })
    },
  )

  await page.goto("/updates")

  await expect(page.getByRole("heading", { name: "Updates" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "v1.11.1" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "v1.11.0" })).toBeVisible()
  await expect(page.getByText("Features", { exact: true })).toBeVisible()
  await expect(page.getByText("Fixes", { exact: true })).toBeVisible()
  await expect(page.getByText("Other", { exact: true })).toBeVisible()
  await expect(page.getByText("feat(records): add run history")).toBeVisible()
  await expect(
    page.getByText("fix(records): highlight current pb"),
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
  await page.route(
    "https://api.github.com/repos/kzcharm/gokz-top-v2/releases?per_page=20",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(releasesPayload),
      })
    },
  )
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
