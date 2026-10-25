import { expect, type Page } from "@playwright/test"

/** Wide columns scroll inside the leaderboard card, without widening the page. */
export async function expectContainedLeaderboardTable(page: Page) {
  const container = page.locator('[data-slot="table-container"]').first()
  for (const width of [1600, 1188, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
        ),
      )
      .toBeLessThanOrEqual(1)
    await expect(container).toHaveCSS("overflow-x", "auto")
    await expect
      .poll(() =>
        container.evaluate((element) => {
          const bounds = element.getBoundingClientRect()
          const card = element
            .closest('[data-slot="card"]')!
            .getBoundingClientRect()
          return bounds.left >= card.left && bounds.right <= card.right + 1
        }),
      )
      .toBe(true)
    await expect
      .poll(() =>
        container.evaluate((element) => {
          element.scrollLeft = element.scrollWidth
          const lastCell = element.querySelector("thead th:last-child")!
          return (
            lastCell.getBoundingClientRect().right -
            element.getBoundingClientRect().right
          )
        }),
      )
      .toBeLessThanOrEqual(1)
    await container.evaluate((element) => {
      element.scrollLeft = 0
    })
  }
  await page.setViewportSize({ width: 1600, height: 900 })
}
