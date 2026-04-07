import { expect, test, type Page } from "@playwright/test"
import { superUserSteamid64 } from "./config"
import { randomSteamid64 } from "./utils/random"
import { logInUser } from "./utils/user"

const sidebarLayoutStorageKey = "gokz-sidebar-layout-v1"

async function getTopLevelSidebarLabels(page: Page) {
  return (await page
    .locator(
      '[data-testid="sidebar-root"] > li > [data-slot="sidebar-menu-button"]',
    )
    .allTextContents()).map((text) => text.trim())
}

async function openOthersFolder(page: Page) {
  const othersButton = page.getByRole("button", { name: "Others" })
  await othersButton.click()
  await expect(page.getByRole("link", { name: "Bans" })).toHaveCount(1)
}

async function dragSidebarItem(
  page: Page,
  sourceSelector: string,
  targetSelector: string,
) {
  const dataTransfer = await page.evaluateHandle(() => new DataTransfer())
  const source = page.locator(sourceSelector)
  const target = page.locator(targetSelector)

  await source.dispatchEvent("dragstart", { dataTransfer })
  await target.dispatchEvent("dragover", { dataTransfer })
  await target.dispatchEvent("drop", { dataTransfer })
}

test.describe("Custom sidebar layout", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Default sidebar puts Bans inside Others", async ({ page }) => {
    await logInUser(page, randomSteamid64())

    await expect(page.getByRole("button", { name: "Others" })).toBeVisible()
    await expect(page.getByRole("link", { name: "Bans" })).toHaveCount(0)

    await openOthersFolder(page)
  })

  test("Dragging a top-level item changes its order and persists after reload", async ({
    page,
  }) => {
    await logInUser(page, randomSteamid64())

    await dragSidebarItem(
      page,
      '[data-testid="sidebar-item-settings"] [data-slot="sidebar-menu-button"]',
      '[data-testid="sidebar-item-profile"]',
    )

    await expect.poll(() => getTopLevelSidebarLabels(page)).toEqual([
      "Servers",
      "Settings",
      "Profile",
      "Leaderboards",
      "Dashboard",
      "Maps",
      "Live",
      "Others",
    ])

    await page.reload()

    await expect.poll(() => getTopLevelSidebarLabels(page)).toEqual([
      "Servers",
      "Settings",
      "Profile",
      "Leaderboards",
      "Dashboard",
      "Maps",
      "Live",
      "Others",
    ])
  })

  test("Dragging an item into Others persists after reload", async ({ page }) => {
    await logInUser(page, randomSteamid64())

    await dragSidebarItem(
      page,
      '[data-testid="sidebar-item-settings"] [data-slot="sidebar-menu-button"]',
      '[data-testid="sidebar-group-others"] [data-slot="sidebar-menu-button"]',
    )

    await expect.poll(() => getTopLevelSidebarLabels(page)).toEqual([
      "Servers",
      "Profile",
      "Leaderboards",
      "Dashboard",
      "Maps",
      "Live",
      "Others",
    ])

    await page.reload()
    await page.getByRole("button", { name: "Others" }).click()
    await expect(page.getByRole("link", { name: "Settings" })).toBeVisible()
    await expect(page.getByRole("link", { name: "Bans" })).toBeVisible()
  })

  test("Dragging an item out of Others persists after reload", async ({ page }) => {
    await logInUser(page, randomSteamid64())
    await openOthersFolder(page)

    await dragSidebarItem(
      page,
      '[data-testid="sidebar-item-bans"] [data-slot="sidebar-menu-sub-button"]',
      '[data-testid="sidebar-item-leaderboards"]',
    )

    await expect.poll(() => getTopLevelSidebarLabels(page)).toEqual([
      "Servers",
      "Profile",
      "Bans",
      "Leaderboards",
      "Dashboard",
      "Maps",
      "Live",
      "Settings",
    ])

    await page.reload()
    await expect.poll(() => getTopLevelSidebarLabels(page)).toEqual([
      "Servers",
      "Profile",
      "Bans",
      "Leaderboards",
      "Dashboard",
      "Maps",
      "Live",
      "Settings",
    ])
    await expect(page.getByRole("button", { name: "Others" })).toHaveCount(0)
  })

  test("Superuser admin group stays fixed at the bottom and is not draggable", async ({
    page,
  }) => {
    await logInUser(page, superUserSteamid64, { isSuperuser: true })

    await dragSidebarItem(
      page,
      '[data-testid="sidebar-group-others"] [data-slot="sidebar-menu-button"]',
      '[data-testid="sidebar-item-servers"]',
    )

    await expect.poll(() => getTopLevelSidebarLabels(page)).toEqual([
      "Others",
      "Servers",
      "Profile",
      "Leaderboards",
      "Dashboard",
      "Maps",
      "Live",
      "Settings",
      "Admin",
    ])

    const adminButton = page.locator(
      '[data-testid="sidebar-group-admin"] [data-slot="sidebar-menu-button"]',
    )
    await expect(adminButton).not.toHaveAttribute("draggable", "true")

    await adminButton.click()
    const adminLinks = page.locator(
      '[data-testid="sidebar-group-admin-content"] [data-slot="sidebar-menu-sub-button"]',
    )
    await expect(adminLinks).toHaveCount(2)
    await expect(adminLinks.nth(0)).not.toHaveAttribute("draggable", "true")
    await expect(adminLinks.nth(1)).not.toHaveAttribute("draggable", "true")
  })

  test("Root redirects to the first saved leaf item", async ({ page }) => {
    await logInUser(page, randomSteamid64())

    await page.evaluate(([storageKey]) => {
      localStorage.setItem(
        storageKey,
        JSON.stringify({
          topLevel: [
            "dashboard",
            "servers",
            "profile",
            "leaderboards",
            "maps",
            "live",
            "settings",
            "others",
          ],
          others: ["bans"],
        }),
      )
    }, [sidebarLayoutStorageKey])

    await page.goto("/")
    await expect(page).toHaveURL(/\/dashboard\/records$/)
  })

  test("Root redirects into Others when the folder is first", async ({ page }) => {
    await logInUser(page, randomSteamid64())

    await page.evaluate(([storageKey]) => {
      localStorage.setItem(
        storageKey,
        JSON.stringify({
          topLevel: [
            "others",
            "servers",
            "profile",
            "leaderboards",
            "dashboard",
            "maps",
            "live",
            "settings",
          ],
          others: ["bans"],
        }),
      )
    }, [sidebarLayoutStorageKey])

    await page.goto("/")
    await expect(page).toHaveURL(/\/bans$/)
  })
})
