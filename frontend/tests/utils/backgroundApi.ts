import type { Page } from "@playwright/test"

/** Keep unrelated authenticated shell queries inside mocked-page tests. */
export async function stubBackgroundApi(page: Page) {
  const responses: Array<[string, unknown]> = [
    ["**/v1/me/settings", {}],
    ["**/v1/me/notifications/unread-count", { unread_count: 0 }],
    ["**/v1/me/hidden-maps", { data: [], count: 0 }],
    ["**/v1/media/posts?limit=1", { data: [], count: 0 }],
  ]
  for (const [url, body] of responses) {
    await page.route(url, async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback()
        return
      }
      await route.fulfill({ json: body })
    })
  }
}
