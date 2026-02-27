import { expect, test } from "@playwright/test"
import { randomItemDescription, randomItemTitle, randomSteamid64 } from "./utils/random"
import { logInUser } from "./utils/user"

test("Items page is accessible and shows correct title", async ({ page }) => {
  await page.goto("/items")
  await expect(page.getByRole("heading", { name: "Items" })).toBeVisible()
  await expect(page.getByText("Create and manage your items")).toBeVisible()
})

test.describe("Items management", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await logInUser(page, randomSteamid64())
    await page.goto("/items")
  })

  test("Create a new item successfully", async ({ page }) => {
    const title = randomItemTitle()
    const description = randomItemDescription()

    await page.getByRole("button", { name: "Add Item" }).click()
    await page.getByLabel("Title").fill(title)
    await page.getByLabel("Description").fill(description)
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("Item created successfully")).toBeVisible()
    await expect(page.getByText(title)).toBeVisible()
  })

  test("Delete an item successfully", async ({ page }) => {
    const title = randomItemTitle()

    await page.getByRole("button", { name: "Add Item" }).click()
    await page.getByLabel("Title").fill(title)
    await page.getByRole("button", { name: "Save" }).click()
    await expect(page.getByText("Item created successfully")).toBeVisible()

    const itemRow = page.getByRole("row").filter({ hasText: title })
    await itemRow.getByRole("button").last().click()
    await page.getByRole("menuitem", { name: "Delete Item" }).click()
    await page.getByRole("button", { name: "Delete" }).click()

    await expect(
      page.getByText("The item was deleted successfully"),
    ).toBeVisible()
  })
})
