import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const consentMessage =
  "We use Google Analytics to improve your experience. Do you accept our use of cookies?"

test("analytics consent banner is hidden in local dev by default", async ({
  page,
}) => {
  let googleTagRequests = 0
  await page.route(/googletagmanager\.com\/gtag\/js/, async (route) => {
    googleTagRequests += 1
    await route.fulfill({ status: 204 })
  })

  await page.goto("/not-found-for-analytics")

  await expect(page.getByRole("heading", { name: consentMessage })).toBeHidden()
  expect(googleTagRequests).toBe(0)
})

test("analytics consent banner can be previewed locally and rejected", async ({
  page,
}) => {
  let googleTagRequests = 0
  await page.route(/googletagmanager\.com\/gtag\/js/, async (route) => {
    googleTagRequests += 1
    await route.fulfill({ status: 204 })
  })

  await page.goto("/not-found-for-analytics?analytics-consent-preview=1")

  await expect(
    page.getByRole("heading", { name: consentMessage }),
  ).toBeVisible()
  await page.getByRole("button", { name: "No, thanks" }).click()

  await expect(page.getByRole("heading", { name: consentMessage })).toBeHidden()
  await expect(
    page.evaluate(() => localStorage.getItem("gokz-analytics-consent")),
  ).resolves.toBe("v1:rejected")
  expect(googleTagRequests).toBe(0)
})

test("local banner preview accept stores consent without loading GA in dev", async ({
  page,
}) => {
  let googleTagRequests = 0
  await page.route(/googletagmanager\.com\/gtag\/js/, async (route) => {
    googleTagRequests += 1
    await route.fulfill({ status: 204 })
  })

  await page.goto("/not-found-for-analytics?analytics-consent-preview=1")

  await page.getByRole("button", { name: "Accept" }).click()

  await expect(page.getByRole("heading", { name: consentMessage })).toBeHidden()
  await expect(
    page.evaluate(() => localStorage.getItem("gokz-analytics-consent")),
  ).resolves.toBe("v1:accepted")
  expect(googleTagRequests).toBe(0)
})

test("local banner preview can be triggered from the console helper", async ({
  page,
}) => {
  await page.goto("/profile/lbgdre")

  await expect(page.getByRole("heading", { name: consentMessage })).toBeHidden()
  await expect
    .poll(() =>
      page.evaluate(() => typeof window.previewAnalyticsConsentBanner),
    )
    .toBe("function")

  await page.evaluate(() => {
    window.previewAnalyticsConsentBanner?.()
  })

  await expect(
    page.getByRole("heading", { name: consentMessage }),
  ).toBeVisible()
})

test("local banner preview survives root route redirects", async ({ page }) => {
  await page.goto("/?analytics-consent-preview=1")

  await expect(
    page.getByRole("heading", { name: consentMessage }),
  ).toBeVisible()
  await expect(
    page.evaluate(() => localStorage.getItem("gokz-analytics-consent-preview")),
  ).resolves.toBe("1")
})
