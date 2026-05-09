import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

function createMap(index: number) {
  const paddedIndex = `${index}`.padStart(2, "0")
  const baseTier = (index % 8) + 1

  return {
    id: 980000 + index,
    name: `kz_map_${paddedIndex}`,
    filesize: 125000 + index,
    validated: index % 2 === 0,
    tiers: {
      OVR: baseTier,
      KZT: baseTier,
      SKZ: baseTier,
      VNL: baseTier,
    },
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

test("Language selector switches locale and persists after reload", async ({
  page,
}) => {
  const seededMaps = Array.from({ length: 12 }, (_, index) =>
    createMap(index + 1),
  )

  await page.route(/\/v1\/maps(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seededMaps),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.goto("/maps")

  await expect(page.getByRole("heading", { name: "Maps" })).toBeVisible()
  await page.getByRole("button", { name: /Select language/ }).click()
  await page.getByText("Русский").click()

  await expect(page.getByRole("heading", { name: "Карты" })).toBeVisible()
  await expect(page.getByText("Загружено карт: 12")).toBeVisible()
  await expect(page.getByText("Показано карт: 12")).toBeVisible()

  await page.reload()

  await expect(page.getByRole("heading", { name: "Карты" })).toBeVisible()
  await expect(page.getByText("Загружено карт: 12")).toBeVisible()
  await expect(
    page.evaluate(() => localStorage.getItem("gokz-language")),
  ).resolves.toBe("ru")
})
