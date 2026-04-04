import { expect, type Page, type Route, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const targetSteamid64 = "76561198000000011"
const currentUserSteamid64 = "76561198000000022"
const otherFollowingSteamid64 = "76561198000000044"

type FollowSummary = {
  follower_count: number
  following_count: number
  viewer_is_following: boolean | null
  viewer_is_self: boolean
}

function createAccessToken(steamid64: string) {
  const header = Buffer.from(
    JSON.stringify({ alg: "none", typ: "JWT" }),
  ).toString("base64url")
  const payload = Buffer.from(JSON.stringify({ sub: steamid64 })).toString(
    "base64url",
  )
  return `${header}.${payload}.signature`
}

function buildPlayer({
  alias,
  name,
  profileViews = 0,
  steamid64,
}: {
  alias: string
  name: string
  profileViews?: number
  steamid64: string
}) {
  return {
    name,
    alias,
    custom_id: null,
    avatar_hash: null,
    country: "DE",
    created_at: "2026-03-01T12:00:00Z",
    last_played_at: "2026-03-31T12:00:00Z",
    updated_at: "2026-03-31T12:00:00Z",
    steamid64,
    profile_views: profileViews,
  }
}

async function stubLoginRedirect(page: Page) {
  await page.route(/\/v1\/login\/steam$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/html",
      body: "<!doctype html><title>Steam Login</title><body>Steam Login</body>",
    })
  })
}

async function installProfileRoutes({
  page,
  currentUser,
  followers = [],
  following = [],
  player = buildPlayer({
    steamid64: targetSteamid64,
    name: "Target Runner",
    alias: "Target Alias",
    profileViews: 37,
  }),
  summary,
}: {
  page: Page
  currentUser?: ReturnType<typeof buildPlayer>
  followers?: Array<ReturnType<typeof buildPlayer>>
  following?: Array<ReturnType<typeof buildPlayer>>
  player?: ReturnType<typeof buildPlayer>
  summary: FollowSummary
}) {
  const playersBySteamid64 = new Map(
    [player, currentUser, ...followers, ...following]
      .filter(
        (entry): entry is ReturnType<typeof buildPlayer> => entry !== undefined,
      )
      .map((entry) => [entry.steamid64, entry]),
  )

  await page.route(/\/v1\/users\/me$/, async (route: Route) => {
    if (!currentUser) {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Unauthorized" }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "019e0000-0000-7000-8000-000000000001",
        steamid64: currentUser.steamid64,
        is_active: true,
        is_superuser: false,
      }),
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

  await page.route(/\/v1\/players\/[^/]+\/views$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ profile_views: player.profile_views }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/follow-summary$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(summary),
      })
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/followers(\?.*)?$/,
    async (route: Route) => {
      const url = new URL(route.request().url())
      const offset = Number(url.searchParams.get("offset") ?? "0")
      const limit = Number(url.searchParams.get("limit") ?? "20")
      const data = followers.slice(offset, offset + limit)

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data,
          count: followers.length,
        }),
      })
    },
  )

  await page.route(
    /\/v1\/players\/[^/]+\/following(\?.*)?$/,
    async (route: Route) => {
      const url = new URL(route.request().url())
      const offset = Number(url.searchParams.get("offset") ?? "0")
      const limit = Number(url.searchParams.get("limit") ?? "20")
      const data = following.slice(offset, offset + limit)

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data,
          count: following.length,
        }),
      })
    },
  )

  await page.route(/\/v1\/players\/[^/]+$/, async (route: Route) => {
    const steamid64 = route.request().url().split("/").pop()
    const requestedPlayer = steamid64 ? playersBySteamid64.get(steamid64) : null

    if (!requestedPlayer) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Player not found" }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(requestedPlayer),
    })
  })
}

test("Logged-out profile shows the shared player context menu without follow", async ({
  page,
}) => {
  await installProfileRoutes({
    page,
    summary: {
      follower_count: 12,
      following_count: 4,
      viewer_is_following: null,
      viewer_is_self: false,
    },
  })

  await page.goto(`/profile/${targetSteamid64}`)

  await expect(
    page.getByRole("heading", { name: "Target Alias" }),
  ).toBeVisible()
  await expect(page.getByTestId("profile-followers-card")).toContainText("12")
  await page.getByTestId("profile-identity-surface").click({ button: "right" })
  await expect(page.getByTestId("profile-identity-context-menu")).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Goto Profile" }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Steam Profile" }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Copy SteamID64" }),
  ).toBeVisible()
  await expect(page.getByRole("menuitem", { name: "Copy Name" })).toBeVisible()
  await expect(page.getByTestId("profile-follow-menu-item")).toHaveCount(0)
})

test("Logged-in user can follow another player and sees state update", async ({
  page,
}) => {
  let summary: FollowSummary = {
    follower_count: 2,
    following_count: 7,
    viewer_is_following: false,
    viewer_is_self: false,
  }

  const currentUser = buildPlayer({
    steamid64: currentUserSteamid64,
    name: "Viewer Runner",
    alias: "Viewer Alias",
  })

  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, createAccessToken(currentUserSteamid64))

  await installProfileRoutes({
    page,
    currentUser,
    summary,
  })

  await page.route(/\/v1\/players\/[^/]+\/follow$/, async (route: Route) => {
    if (route.request().method() === "POST") {
      summary = {
        ...summary,
        follower_count: summary.follower_count + 1,
        viewer_is_following: true,
      }
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(summary),
    })
  })

  await page.goto(`/profile/${targetSteamid64}`)

  await expect(page.getByTestId("profile-followers-card")).toContainText("2")
  await page.getByTestId("profile-identity-surface").click({ button: "right" })

  const followMenuItem = page.getByTestId("profile-follow-menu-item")
  await expect(page.getByTestId("profile-identity-context-menu")).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Goto Profile" }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Steam Profile" }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Copy SteamID64" }),
  ).toBeVisible()
  await expect(page.getByRole("menuitem", { name: "Copy Name" })).toBeVisible()
  await expect(followMenuItem).toHaveText("Follow")

  await followMenuItem.click()

  await expect(page.getByTestId("profile-followers-card")).toContainText("3")
})

test("Logged-in user can unfollow and sees state update", async ({ page }) => {
  let summary: FollowSummary = {
    follower_count: 5,
    following_count: 9,
    viewer_is_following: true,
    viewer_is_self: false,
  }

  const currentUser = buildPlayer({
    steamid64: currentUserSteamid64,
    name: "Viewer Runner",
    alias: "Viewer Alias",
  })

  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, createAccessToken(currentUserSteamid64))

  await installProfileRoutes({
    page,
    currentUser,
    summary,
  })

  await page.route(/\/v1\/players\/[^/]+\/follow$/, async (route: Route) => {
    if (route.request().method() === "DELETE") {
      summary = {
        ...summary,
        follower_count: summary.follower_count - 1,
        viewer_is_following: false,
      }
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(summary),
    })
  })

  await page.goto(`/profile/${targetSteamid64}`)

  await expect(page.getByTestId("profile-followers-card")).toContainText("5")
  await page.getByTestId("profile-identity-surface").click({ button: "right" })

  const followMenuItem = page.getByTestId("profile-follow-menu-item")
  await expect(page.getByTestId("profile-identity-context-menu")).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Goto Profile" }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Steam Profile" }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Copy SteamID64" }),
  ).toBeVisible()
  await expect(page.getByRole("menuitem", { name: "Copy Name" })).toBeVisible()
  await expect(followMenuItem).toHaveText("Unfollow")

  await followMenuItem.click()

  await expect(page.getByTestId("profile-followers-card")).toContainText("4")
})

test("Own profile keeps the shared player context menu without follow", async ({
  page,
}) => {
  const currentUser = buildPlayer({
    steamid64: targetSteamid64,
    name: "Target Runner",
    alias: "Target Alias",
  })

  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, createAccessToken(targetSteamid64))

  await installProfileRoutes({
    page,
    currentUser,
    player: currentUser,
    summary: {
      follower_count: 8,
      following_count: 3,
      viewer_is_following: false,
      viewer_is_self: true,
    },
  })

  await page.goto(`/profile/${targetSteamid64}`)

  await expect(
    page.getByRole("heading", { name: "Target Alias" }),
  ).toBeVisible()
  await page.getByTestId("profile-identity-surface").click({ button: "right" })
  await expect(page.getByTestId("profile-identity-context-menu")).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Goto Profile" }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Steam Profile" }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Copy SteamID64" }),
  ).toBeVisible()
  await expect(page.getByRole("menuitem", { name: "Copy Name" })).toBeVisible()
  await expect(page.getByTestId("profile-follow-menu-item")).toHaveCount(0)
})

test("Logged-in user can browse social lists and navigate to another profile", async ({
  page,
}) => {
  const currentUser = buildPlayer({
    steamid64: currentUserSteamid64,
    name: "Viewer Runner",
    alias: "Viewer Alias",
  })
  const followers = Array.from({ length: 21 }, (_, index) =>
    buildPlayer({
      steamid64: (BigInt("76561198010000000") + BigInt(index)).toString(),
      name: `Follower ${index + 1}`,
      alias: `Follower Alias ${index + 1}`,
    }),
  )
  const following = [
    buildPlayer({
      steamid64: otherFollowingSteamid64,
      name: "Following Runner",
      alias: "Following Alias",
    }),
  ]
  const followerOffsets: number[] = []

  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, createAccessToken(currentUserSteamid64))

  await installProfileRoutes({
    page,
    currentUser,
    followers,
    following,
    summary: {
      follower_count: followers.length,
      following_count: following.length,
      viewer_is_following: false,
      viewer_is_self: false,
    },
  })

  await page.route(
    /\/v1\/players\/[^/]+\/followers(\?.*)?$/,
    async (route: Route) => {
      const url = new URL(route.request().url())
      const offset = Number(url.searchParams.get("offset") ?? "0")
      const limit = Number(url.searchParams.get("limit") ?? "20")
      followerOffsets.push(offset)

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: followers.slice(offset, offset + limit),
          count: followers.length,
        }),
      })
    },
  )

  await page.goto(`/profile/${targetSteamid64}`)

  await page.getByTestId("profile-followers-card").click()
  await expect(page.getByTestId("profile-social-dialog")).toBeVisible()
  await expect(
    page.getByTestId(`profile-social-row-${followers[0].steamid64}`),
  ).toBeVisible()
  await expect(
    page.getByTestId(`profile-social-row-${followers[19].steamid64}`),
  ).toBeVisible()
  await expect(
    page.getByTestId(`profile-social-row-${followers[20].steamid64}`),
  ).toHaveCount(0)

  await page.getByRole("button", { name: "Load more" }).click()
  await expect(
    page.getByTestId(`profile-social-row-${followers[20].steamid64}`),
  ).toBeVisible()
  expect(followerOffsets).toEqual([0, 20])

  await page.getByRole("tab", { name: /Following 1/ }).click()
  await expect(page.getByText("Following Alias")).toBeVisible()
  await page
    .getByTestId(`profile-social-row-${otherFollowingSteamid64}`)
    .click({ button: "right" })
  await expect(page.getByTestId("player-follow-menu-item")).toBeVisible()
  await expect(page.getByTestId("player-follow-menu-item")).toHaveText("Follow")

  await page.getByRole("link", { name: /Following Alias/ }).click()
  await expect(page).toHaveURL(
    new RegExp(`/profile/${otherFollowingSteamid64}$`),
  )
  await expect(
    page.getByRole("heading", { name: "Following Alias" }),
  ).toBeVisible()
})

test("Logged-out user clicking follower lists is sent to log in", async ({
  page,
}) => {
  await stubLoginRedirect(page)
  await installProfileRoutes({
    page,
    summary: {
      follower_count: 6,
      following_count: 2,
      viewer_is_following: null,
      viewer_is_self: false,
    },
  })

  await page.goto(`/profile/${targetSteamid64}`)

  await page.getByTestId("profile-followers-card").click()
  await expect(page).toHaveURL(/\/v1\/login\/steam$/)
})
