import { expect, type Page } from "@playwright/test"

export async function setShowHiddenMaps(page: Page, show: boolean) {
  await page
    .getByRole("button", { name: "Quick preferences", exact: true })
    .click()
  const item = page.getByRole("menuitemcheckbox", {
    name: "Show hidden maps",
    exact: true,
  })
  await expect(page.getByRole("menuitemcheckbox").first()).toHaveText(
    "Show hidden maps",
  )
  if ((await item.getAttribute("aria-checked")) !== String(show))
    await item.click()
  else await page.keyboard.press("Escape")
  await expect(page.getByRole("menu")).toHaveCount(0)
}
