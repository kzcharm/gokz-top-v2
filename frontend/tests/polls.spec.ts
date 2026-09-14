import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const pollId = "01991e61-61d0-7c31-bfb8-4d6d36d2d2b2"
const poll = {
  id: pollId,
  title: "Choose the next community event",
  description: "Pick the event you would most like to play.",
  status: "active",
  ends_at: "2030-07-15T18:30:00Z",
  total_votes: 12,
  max_selections: 1,
  allow_vote_change: true,
  has_voted: false,
  can_view_results: false,
  selected_option_ids: [],
  options: [
    {
      id: "01991e61-61d0-7c31-bfb8-4d6d36d2d2b3",
      label: "Tournament",
      description: null,
      votes: null,
      percentage: null,
    },
    {
      id: "01991e61-61d0-7c31-bfb8-4d6d36d2d2b4",
      label: "Map showcase",
      description: null,
      votes: null,
      percentage: null,
    },
  ],
}
const closedPoll = {
  ...poll,
  id: "01991e61-61d0-7c31-bfb8-4d6d36d2d2b5",
  title: "Archived community poll",
  status: "closed",
  ends_at: null,
  total_votes: 10,
  can_view_results: true,
  options: [
    {
      ...poll.options[0],
      votes: 2,
      percentage: 20,
    },
    {
      ...poll.options[1],
      votes: 7,
      percentage: 70,
    },
    {
      id: "01991e61-61d0-7c31-bfb8-4d6d36d2d2b6",
      label: "Speedrun relay",
      description: null,
      votes: 1,
      percentage: 10,
    },
  ],
}

test.beforeEach(async ({ page }) => {
  await page.route("**/v1/polls?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [poll, closedPoll], count: 2 }),
    })
  })
  await page.route(`**/v1/polls/${pollId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(poll),
    })
  })
  await page.route(`**/v1/polls/${closedPoll.id}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(closedPoll),
    })
  })
})

test("poll cards link to a dedicated route and show the voting deadline", async ({
  page,
}) => {
  await page.goto("/polls")

  const pollLink = page.getByRole("link", {
    name: /Choose the next community event/,
  })
  await expect(pollLink).toHaveAttribute("href", `/polls/${pollId}`)
  await expect(pollLink.getByText("Vote ends")).toBeVisible()
  await expect(
    page
      .getByRole("link", { name: /Archived community poll/ })
      .getByText("Closed"),
  ).toHaveClass(/bg-red-500\/15/)

  await pollLink.click()

  await expect(page).toHaveURL(`/polls/${pollId}`)
  await expect(page.getByRole("dialog")).toContainText(
    "Choose the next community event",
  )
  await expect(page.getByRole("dialog")).toContainText("Vote ends")
  await expect(page.getByRole("dialog")).not.toContainText("2030-07-15")
})

test("a poll route can be opened directly", async ({ page }) => {
  await page.goto(`/polls/${pollId}`)

  const dialog = page.getByRole("dialog")
  await expect(dialog).toContainText("Choose the next community event")
  await expect(dialog.locator("button[aria-pressed]").nth(0)).toContainText(
    /A\.\s*Tournament/,
  )
})

test("visible poll results are ordered by most votes in the details dialog", async ({
  page,
}) => {
  await page.goto(`/polls/${closedPoll.id}`)

  const options = page.getByRole("dialog").locator("button[aria-pressed]")
  await expect(options).toHaveCount(3)
  await expect(options.nth(0)).toContainText(/1\.\s*B\.\s*Map showcase/)
  await expect(options.nth(1)).toContainText(/2\.\s*A\.\s*Tournament/)
  await expect(options.nth(2)).toContainText(/3\.\s*C\.\s*Speedrun relay/)
})
