import { expect, type Page, type Route, test } from "@playwright/test"

const targetSteamid64 = "76561198000000001"
const viewerSteamid64 = "76561198000000002"
const accessToken = "test-access-token"

const player = {
  name: "Comment Target",
  alias: "Target Alias",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64: targetSteamid64,
}

async function installProfileCommentsRoutes(
  page: Page,
  {
    currentUserSteamid64,
    initialComments,
  }: {
    currentUserSteamid64: string | null
    initialComments: Array<{
      id: string
      text: string
      created_at: string
      updated_at: string
      author: { steamid64: string; display_name: string }
    }>
  },
) {
  const comments = [...initialComments]

  if (currentUserSteamid64) {
    await page.addInitScript((token) => {
      localStorage.setItem("access_token", token)
    }, accessToken)
  }

  await page.route(/\/v1\/admin\/servers\/access$/, async (route: Route) => {
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Forbidden" }),
    })
  })

  if (currentUserSteamid64) {
    await page.route(/\/v1\/users\/me$/, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          steamid64: currentUserSteamid64,
          is_active: true,
          roles: [],
        }),
      })
    })
  } else {
    await page.route(/\/v1\/users\/me$/, async (route: Route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Unauthorized" }),
      })
    })
  }

  await page.route(/\/v1\/players\/[^/]+$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(player),
    })
  })

  await page.route(/\/v1\/players\/[^/]+\/views$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ profile_views: 0 }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/stats(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          steamid64: targetSteamid64,
          daily_activity: null,
          playtime: {
            updated_at: "2026-04-03T12:00:00Z",
            total_seconds: 7200,
          },
        }),
      })
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/follow-summary$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          follower_count: 0,
          following_count: 0,
          viewer_is_following: null,
          viewer_is_self: currentUserSteamid64 === targetSteamid64,
        }),
      })
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/pinned-records(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      })
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/jumpstats(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [],
          count: 0,
        }),
      })
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/comments(\/[^/]+)?$/,
    async (route: Route) => {
      const request = route.request()
      const method = request.method()
      const url = new URL(request.url())
      const commentId = url.pathname.split("/").at(-1) ?? ""

      if (method === "POST") {
        const body = request.postDataJSON() as { text?: string } | null
        const createdComment = {
          id: "01970abc-1234-7def-8123-abcdef123456",
          text: body?.text?.trim() ?? "",
          created_at: "2026-05-25T12:00:00Z",
          updated_at: "2026-05-25T12:00:00Z",
          author: {
            steamid64: viewerSteamid64,
            display_name: "Viewer Alias",
          },
        }
        comments.unshift(createdComment)
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(createdComment),
        })
        return
      }

      if (method === "DELETE") {
        const index = comments.findIndex((comment) => comment.id === commentId)
        if (index >= 0) {
          comments.splice(index, 1)
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ message: "Player comment deleted" }),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: comments,
          count: comments.length,
        }),
      })
    },
  )

  await page.route(/\/v1\/graphql$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: {} }),
    })
  })

  await page.route(/\/v1\/bans(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.route(/\/v1\/maps(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  })

  await page.route(
    /\/v1\/leaderboards\/players\/[^/?]+(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rank: null,
          rank_regional: null,
          region: null,
          rating: null,
        }),
      })
    },
  )
}

test("Logged-out viewer sees comments and login prompt", async ({ page }) => {
  await installProfileCommentsRoutes(page, {
    currentUserSteamid64: null,
    initialComments: [
      {
        id: "01970abc-0000-7000-8000-abcdef123456",
        text: "Welcome to the profile.",
        created_at: "2026-05-24T12:00:00Z",
        updated_at: "2026-05-24T12:00:00Z",
        author: {
          steamid64: viewerSteamid64,
          display_name: "Viewer Alias",
        },
      },
    ],
  })

  await page.goto(`/profile/${targetSteamid64}/comments`)

  await expect(page.getByRole("tab", { name: "Comments" })).toHaveAttribute(
    "data-state",
    "active",
  )
  await expect(page.getByTestId("profile-comments-login")).toBeVisible()
  await expect(page.getByTestId("profile-comments-list")).toContainText(
    "Welcome to the profile.",
  )
  await expect(page.getByTestId("profile-comments-form")).toHaveCount(0)
})

test("Logged-in viewer can post and delete a comment", async ({ page }) => {
  await installProfileCommentsRoutes(page, {
    currentUserSteamid64: viewerSteamid64,
    initialComments: [],
  })

  page.on("dialog", (dialog) => dialog.accept())

  await page.goto(`/profile/${targetSteamid64}/comments`)

  await page.getByTestId("profile-comments-form").fill("  Great progress.  ")
  await page.getByRole("button", { name: "Post Comment" }).click()

  await expect(page.getByTestId("profile-comments-list")).toContainText(
    "Great progress.",
  )

  await page
    .getByTestId("profile-comments-list")
    .getByRole("button", { name: "Delete player comment" })
    .click()

  await expect(page.getByTestId("profile-comments-empty")).toBeVisible()
})
