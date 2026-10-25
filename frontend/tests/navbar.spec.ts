import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

test("Desktop navbar centers the current title and follows navigation and language", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname
    await route.fulfill({
      json:
        path === "/v1/maps" || path === "/v1/maps/wrs"
          ? []
          : { data: [], count: 0 },
    })
  })
  await page.goto("/servers")

  const title = page.getByTestId("navbar-page-title")
  await expect(title).toBeVisible()
  await expect(title).toHaveText("Servers")
  await page.screenshot({ path: testInfo.outputPath("desktop-navbar.png") })
  const headerBounds = await page.locator("header").boundingBox()
  const titleBounds = await title.boundingBox()
  expect(headerBounds).not.toBeNull()
  expect(titleBounds).not.toBeNull()
  expect(
    Math.abs(
      titleBounds!.x +
        titleBounds!.width / 2 -
        (headerBounds!.x + headerBounds!.width / 2),
    ),
  ).toBeLessThan(2)

  await page.getByRole("link", { name: "Maps", exact: true }).click()
  await expect(title).toHaveText("Maps")
  await page.getByRole("button", { name: /Select language/ }).click()
  await page.getByText("简体中文").click()
  await expect(title).toHaveText("地图")

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(title).toBeHidden()
})
