import { expect, test } from "@playwright/test"
import { mapImagePixel } from "./utils/mapImages"

test.use({ storageState: { cookies: [], origins: [] } })

for (const scenario of ["local", "workshop", "missing"] as const) {
  test(`Map images select one source: ${scenario}`, async ({ page }) => {
    await page.route("**/__map-image-test", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: "<!doctype html><title>Map image test</title>",
      }),
    )
    const requests: string[] = []
    await page.route("**/v1/maps/images/kz_test.webp", (route) => {
      requests.push("local")
      return scenario === "local"
        ? route.fulfill({ contentType: "image/png", body: mapImagePixel })
        : route.fulfill({ status: 404 })
    })
    await page.route("**/v1/maps/workshop/123/preview-image", (route) => {
      requests.push("workshop")
      return scenario === "missing"
        ? route.fulfill({ status: 404 })
        : route.fulfill({ contentType: "image/png", body: mapImagePixel })
    })
    await page.goto("/__map-image-test")
    const selected = await page.evaluate(async () => {
      const modulePath = "/src/lib/map-images.ts"
      const { loadFirstMapImage } = await import(/* @vite-ignore */ modulePath)
      return loadFirstMapImage([
        "/v1/maps/images/kz_test.webp",
        "/v1/maps/workshop/123/preview-image",
      ])
    })
    expect(selected).toBe(
      scenario === "local"
        ? "/v1/maps/images/kz_test.webp"
        : scenario === "workshop"
          ? "/v1/maps/workshop/123/preview-image"
          : null,
    )
    expect(requests).toEqual(
      scenario === "local" ? ["local"] : ["local", "workshop"],
    )
  })
}
