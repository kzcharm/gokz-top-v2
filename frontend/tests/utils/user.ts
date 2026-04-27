import { expect, type Page } from "@playwright/test"
import { issueSessionToken } from "./privateApi"

export async function logInUser(
  page: Page,
  steamid64?: number,
  opts?: { isSuperuser?: boolean; name?: string },
) {
  const { accessToken } = await issueSessionToken({
    request: page.request,
    steamid64,
    isSuperuser: opts?.isSuperuser ?? false,
    name: opts?.name ?? "Test User",
  })

  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)
  await page.goto("/")
  await expect(page.getByTestId("user-menu")).toBeVisible()
}

export async function logOutUser(page: Page) {
  await page.getByTestId("user-menu").click()
  await page.getByRole("menuitem", { name: "Log Out" }).click()
  await page.waitForURL(/(\/v1\/login\/steam|steamcommunity\.com\/openid)/)
}
