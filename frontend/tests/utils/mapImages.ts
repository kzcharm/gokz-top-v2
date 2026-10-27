import type { Page } from "@playwright/test"

export const mapImagePixel = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jR1sAAAAASUVORK5CYII=",
  "base64",
)

export async function stubMapImageAssets(page: Page) {
  for (const pattern of [
    "**/v1/maps/images/*.webp",
    "https://steam.example/**",
  ]) {
    await page.route(pattern, (route) =>
      route.fulfill({ contentType: "image/png", body: mapImagePixel }),
    )
  }
}
