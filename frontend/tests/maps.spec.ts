import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

function createMap(index: number) {
  const paddedIndex = `${index}`.padStart(2, "0")

  return {
    id: 980000 + index,
    name: `kz_map_${paddedIndex}`,
    filesize: 125000 + index,
    validated: index % 2 === 0,
    difficulty: (index % 8) + 1,
    created_on: `2026-03-${`${(index % 28) + 1}`.padStart(2, "0")}T08:00:00Z`,
    updated_on: `2026-03-${`${(index % 28) + 1}`.padStart(2, "0")}T12:00:00Z`,
    approved_by_steamid64: "76561198003275951",
    workshop_id: 1986459000 + index,
    synced_at: `2026-03-${`${(index % 28) + 1}`.padStart(2, "0")}T15:00:00Z`,
    authors: [],
    no_steamid_names: [],
    workshop_url: `https://steamcommunity.com/sharedfiles/filedetails/?id=${1986459000 + index}`,
  }
}

const seededMaps = Array.from({ length: 30 }, (_, index) =>
  createMap(index + 1),
)

seededMaps[0] = {
  ...seededMaps[0],
  name: "kz_alpha",
  difficulty: 2,
  updated_on: "2026-03-01T12:00:00Z",
}

seededMaps[1] = {
  ...seededMaps[1],
  name: "kz_omega",
  difficulty: 8,
  updated_on: "2026-03-30T12:00:00Z",
}

seededMaps[2] = {
  ...seededMaps[2],
  name: "kz_special_search",
  difficulty: 5,
  updated_on: "2026-03-15T12:00:00Z",
}

test("Maps catalog supports search, sorting, pagination, and placeholder navigation", async ({
  page,
}) => {
  let mapsRequestUrl = ""

  await page.addInitScript(() => {
    localStorage.setItem("gokz-datetime-format", "iso")
  })

  await page.route(/\/v1\/maps(\?.*)?$/, async (route) => {
    mapsRequestUrl = route.request().url()
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seededMaps),
    })
  })

  await page.goto("/maps")

  await expect(page).toHaveURL(/\/maps$/)
  await expect(page.getByRole("heading", { name: "Maps" })).toBeVisible()
  await expect(page.getByText("30 maps loaded")).toBeVisible()
  await expect(page.getByText("Page 1 of 2")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_alpha")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_omega")).toHaveCount(0)

  expect(new URL(mapsRequestUrl).searchParams.get("is_validated")).toBe("true")

  await page
    .getByRole("textbox", { name: "Search maps by name" })
    .fill("special")
  await expect(page.getByTestId("map-card-kz_special_search")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_alpha")).toHaveCount(0)

  await page.getByRole("textbox", { name: "Search maps by name" }).fill("")
  await page.getByRole("combobox", { name: "Sort maps" }).click()
  await page.getByRole("option", { name: "Updated newest-first" }).click()

  const firstCard = page.locator('[data-testid^="map-card-"]').first()
  await expect(firstCard).toHaveAttribute("data-testid", "map-card-kz_omega")

  await page.getByRole("button", { name: "Go to page 2" }).click()
  await expect(page.getByText("Page 2 of 2")).toBeVisible()
  await expect(page.getByTestId("map-card-kz_omega")).toHaveCount(0)
  await expect(page.getByTestId("map-card-kz_alpha")).toBeVisible()

  await page.getByRole("button", { name: "Go to page 1" }).click()
  await page.getByTestId("map-card-kz_omega").click()

  await expect(page).toHaveURL(/\/maps\/kz_omega$/)
  await expect(page.getByRole("heading", { name: "kz_omega" })).toBeVisible()
  await expect(page.getByText(/Map page coming soon/)).toBeVisible()
})
