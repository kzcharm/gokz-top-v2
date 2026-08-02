import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

test("AXE KZ Minor notification dot stays dismissed after opening the link", async ({
  page,
}) => {
  await page.route(/\/v1\/live\/streams(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.goto("/servers")

  const minorLink = page.getByRole("link", { name: "AXE KZ Minor" })
  await expect(
    minorLink.locator('span[aria-hidden="true"].bg-red-500'),
  ).toBeVisible()

  const popupPromise = page.waitForEvent("popup")
  await minorLink.click()
  const popup = await popupPromise
  await popup.close()

  await expect(
    minorLink.locator('span[aria-hidden="true"].bg-red-500'),
  ).toHaveCount(0)
  await expect
    .poll(() =>
      page.evaluate(() => localStorage.getItem("gokz-axe-kz-minor-seen")),
    )
    .toBe("1")

  await page.reload()

  await expect(
    page
      .getByRole("link", { name: "AXE KZ Minor" })
      .locator('span[aria-hidden="true"].bg-red-500'),
  ).toHaveCount(0)
})
