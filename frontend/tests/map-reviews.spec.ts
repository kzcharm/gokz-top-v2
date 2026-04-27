import { expect, type Page, type Route, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const currentUserSteamid64 = "76561198000000001"
const otherUserSteamid64 = "76561198000000022"
const accessToken = "test-review-token"
const mapId = 980200
const mapName = "kz_alpha"

const currentUserResponse = {
  steamid64: currentUserSteamid64,
  is_active: true,
  is_superuser: false,
  created_at: "2026-03-01T12:00:00Z",
  last_visited_at: "2026-03-31T12:00:00Z",
  player: { steamid64: currentUserSteamid64, display_name: "Review Runner" },
}

const mapResponse = {
  id: mapId,
  name: mapName,
  filesize: 125000,
  validated: true,
  tiers: {
    OVR: 4,
    KZT: 4,
    SKZ: 4,
    VNL: 4,
  },
  created_on: "2026-03-01T08:00:00Z",
  updated_on: "2026-03-01T12:00:00Z",
  approved_by_steamid64: "76561198003275951",
  workshop_id: 1986459001,
  synced_at: "2026-03-01T15:00:00Z",
  authors: ["76561198000000003"],
  no_steamid_names: [],
  workshop_url:
    "https://steamcommunity.com/sharedfiles/filedetails/?id=1986459001",
  review_summary: {
    overall_avg: 4.5,
    gameplay_avg: 4.0,
    visuals_avg: 4.0,
    reviews_count: 2,
    gameplay_count: 2,
    visuals_count: 2,
    comments_count: 2,
    updated_at: "2026-03-31T12:00:00Z",
  },
}

const mapLeaderboardRecord = {
  uuid: "019e1111-1111-7111-8111-111111111111",
  id: 980900,
  player: { steamid64: currentUserSteamid64, display_name: "Review Runner" },
  steam_id: null,
  server_id: 980300,
  server_name: "Alpha Server",
  map_id: mapId,
  map_name: mapName,
  map_tier: 4,
  mode_id: 200,
  mode: "KZT",
  stage: 0,
  tickrate: 128,
  time: 41.123,
  teleports: 0,
  points: 415,
  created_on: "2026-03-31T12:00:00Z",
  updated_on: "2026-03-31T12:00:00Z",
  updated_by: currentUserSteamid64,
  replay_id: null,
  is_valid: true,
}

type ReviewRow = {
  steamid64: string
  map_id: number
  server_group_id: string | null
  content: {
    overall: number
    gameplay: number | null
    visuals: number | null
    comment: {
      text: string
      language: string
      created_at: string
      updated_at: string
    } | null
  }
  created_at: string
  updated_at: string
  player: {
    steamid64: string
    display_name: string
  }
  map: {
    id: number
    name: string
  }
}

async function stubRegions(page: Page) {
  await page.route("**/v1/regions/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        count: 1,
        data: [{ code: "EU", name: "Europe", country_codes: ["DE"] }],
      }),
    })
  })
}

async function installMapReviewRoutes(page: Page) {
  let reviewRows: ReviewRow[] = [
    {
      steamid64: currentUserSteamid64,
      map_id: mapId,
      server_group_id: "019e0000-0000-7000-8000-000000000001",
      content: {
        overall: 4,
        gameplay: 5,
        visuals: 4,
        comment: {
          text: "Latest server-group note",
          language: "en",
          created_at: "2026-03-30T12:00:00Z",
          updated_at: "2026-03-30T12:00:00Z",
        },
      },
      created_at: "2026-03-30T12:00:00Z",
      updated_at: "2026-03-30T12:00:00Z",
      player: {
        steamid64: currentUserSteamid64,
        display_name: "Review Runner",
      },
      map: {
        id: mapId,
        name: mapName,
      },
    },
    {
      steamid64: otherUserSteamid64,
      map_id: mapId,
      server_group_id: null,
      content: {
        overall: 5,
        gameplay: 4,
        visuals: 4,
        comment: {
          text: "Another player comment",
          language: "en",
          created_at: "2026-03-29T12:00:00Z",
          updated_at: "2026-03-29T12:00:00Z",
        },
      },
      created_at: "2026-03-29T12:00:00Z",
      updated_at: "2026-03-29T12:00:00Z",
      player: {
        steamid64: otherUserSteamid64,
        display_name: "Other Player",
      },
      map: {
        id: mapId,
        name: mapName,
      },
    },
  ]

  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)

  await stubRegions(page)

  await page.route(/\/v1\/users\/me$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(currentUserResponse),
    })
  })

  await page.route(/\/v1\/maps\/name\/[^/?]+(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mapResponse),
    })
  })

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([mapLeaderboardRecord]),
    })
  })

  await page.route(/\/v1\/maps\/reviews(\?.*)?$/, async (route: Route) => {
    const method = route.request().method()
    const url = new URL(route.request().url())
    const requestedMapId = Number(url.searchParams.get("map_id"))
    if (requestedMapId !== mapId) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
      return
    }

    if (method === "GET") {
      const steamid64 = url.searchParams.get("steamid64")
      const source = url.searchParams.get("source") ?? "latest"
      const withCommentsOnly =
        url.searchParams.get("with_comments_only") === "true"
      let filteredRows = reviewRows.filter((review) => review.map_id === mapId)

      if (steamid64) {
        filteredRows = filteredRows.filter(
          (review) => review.steamid64 === steamid64,
        )
      }

      if (source === "website") {
        filteredRows = filteredRows.filter(
          (review) => review.server_group_id === null,
        )
      } else {
        const latestByPlayer = new Map<string, ReviewRow>()
        for (const review of filteredRows) {
          const current = latestByPlayer.get(review.steamid64)
          if (
            !current ||
            Date.parse(review.updated_at) > Date.parse(current.updated_at)
          ) {
            latestByPlayer.set(review.steamid64, review)
          }
        }
        filteredRows = Array.from(latestByPlayer.values())
      }

      if (withCommentsOnly) {
        filteredRows = filteredRows.filter(
          (review) => review.content.comment?.text.trim().length,
        )
      }

      filteredRows = filteredRows.toSorted(
        (left, right) =>
          Date.parse(right.updated_at) - Date.parse(left.updated_at),
      )

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: filteredRows,
          count: filteredRows.length,
        }),
      })
      return
    }

    if (method === "PUT") {
      const body = route.request().postDataJSON() as {
        map_id: number
        content: {
          overall: number
          gameplay: number | null
          visuals: number | null
          comment: { text: string } | null
        }
      }

      const updatedAt = "2026-03-31T18:00:00Z"
      const websiteRow = reviewRows.find(
        (review) =>
          review.steamid64 === currentUserSteamid64 &&
          review.map_id === body.map_id &&
          review.server_group_id === null,
      )
      const nextRow: ReviewRow = {
        steamid64: currentUserSteamid64,
        map_id: body.map_id,
        server_group_id: null,
        content: {
          overall: body.content.overall,
          gameplay: body.content.gameplay,
          visuals: body.content.visuals,
          comment: body.content.comment
            ? {
                text: body.content.comment.text,
                language: "en",
                created_at:
                  websiteRow?.content.comment?.created_at ?? updatedAt,
                updated_at: updatedAt,
              }
            : null,
        },
        created_at: websiteRow?.created_at ?? updatedAt,
        updated_at: updatedAt,
        player: {
          steamid64: currentUserSteamid64,
          display_name: "Review Runner",
        },
        map: {
          id: mapId,
          name: mapName,
        },
      }

      reviewRows = [
        ...reviewRows.filter(
          (review) =>
            !(
              review.steamid64 === currentUserSteamid64 &&
              review.map_id === body.map_id &&
              review.server_group_id === null
            ),
        ),
        nextRow,
      ]

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(nextRow),
      })
      return
    }

    reviewRows = reviewRows.map((review) => {
      if (
        review.steamid64 !== currentUserSteamid64 ||
        review.map_id !== mapId
      ) {
        return review
      }
      return {
        ...review,
        content: {
          ...review.content,
          comment: null,
        },
        updated_at: "2026-03-31T19:00:00Z",
      }
    })

    const latestRemainingReview = reviewRows
      .filter(
        (review) =>
          review.steamid64 === currentUserSteamid64 && review.map_id === mapId,
      )
      .toSorted(
        (left, right) =>
          Date.parse(right.updated_at) - Date.parse(left.updated_at),
      )[0]

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(latestRemainingReview),
    })
  })
}

async function installProfileReviewRoutes(
  page: Page,
  profileSteamid64: string,
) {
  await page.route(/\/v1\/users\/me$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...currentUserResponse,
        steamid64: currentUserSteamid64,
        player: {
          steamid64: currentUserSteamid64,
          display_name: "Review Runner",
        },
      }),
    })
  })

  await page.route(/\/v1\/players\/[^/]+$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        name: "Review Runner",
        alias: "Review Runner",
        custom_id: null,
        avatar_hash: null,
        country: "DE",
        created_at: "2026-03-01T12:00:00Z",
        last_played_at: "2026-03-31T12:00:00Z",
        updated_at: "2026-03-31T12:00:00Z",
        steamid64: profileSteamid64,
        profile_views: 7,
      }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/follow-summary$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          follower_count: 2,
          following_count: 3,
          viewer_is_following: false,
          viewer_is_self: profileSteamid64 === currentUserSteamid64,
        }),
      })
    },
  )

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

  await page.route(
    /\/v1\/leaderboards\/players\/[^?]+(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rank: 42,
          rank_regional: 7,
          region: "EU",
          rating: 5.5,
          player: {
            steamid64: profileSteamid64,
            display_name: "Review Runner",
          },
          scope: "OVR",
        }),
      })
    },
  )

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([mapLeaderboardRecord]),
    })
  })

  await page.route(/\/v1\/records\/rank(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], count: 0 }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/pinned-records(\?.*)?$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: [], count: 0 }),
      })
    },
  )
}

test("Map detail review dialog prefills latest review, saves website review, and deletes comments", async ({
  page,
}) => {
  await installMapReviewRoutes(page)

  await page.goto(`/maps/${mapName}`)
  await page.getByRole("tab", { name: "Reviews" }).click()

  await expect(page.getByTestId("map-add-review-button")).toBeVisible()
  await page.getByTestId("map-add-review-button").click()

  await expect(page.getByLabel("Comment")).toHaveValue(
    "Latest server-group note",
  )

  await page.getByLabel("Comment").fill("Website-ready note")
  await page.getByRole("button", { name: "Save review" }).click()

  await expect(page.getByRole("dialog")).toHaveCount(0)

  await page.goto(`/maps/${mapName}`)
  await page.getByRole("tab", { name: "Reviews" }).click()
  await page.getByTestId("map-add-review-button").click()
  page.once("dialog", (dialog) => dialog.accept())
  await page.getByRole("button", { name: "Delete comments" }).click()

  await expect(page.getByLabel("Comment")).toHaveValue("")
  await expect(page.getByTestId("map-review-overall-star-4")).toHaveAttribute(
    "aria-pressed",
    "true",
  )
})

test("Own profile map context menu includes Add review", async ({ page }) => {
  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)
  await installProfileReviewRoutes(page, currentUserSteamid64)
  await page.goto(`/profile/${currentUserSteamid64}/records`)

  await page.getByRole("link", { name: mapName }).click({
    button: "right",
  })

  await expect(page.getByRole("menuitem", { name: "Add review" })).toBeVisible()
})

test("Other player profile map context menu omits Add review", async ({
  page,
}) => {
  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)
  await installProfileReviewRoutes(page, otherUserSteamid64)
  await page.goto(`/profile/${otherUserSteamid64}/records`)

  await page.getByRole("link", { name: mapName }).click({
    button: "right",
  })

  await expect(page.getByRole("menuitem", { name: "Add review" })).toHaveCount(
    0,
  )
})
