import { expect, type Page, type Route, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

const steamid64 = "76561198000000001"
const accessToken = "test-access-token"

const player = {
  name: "Pinned Runner",
  alias: "Pinned Alias",
  custom_id: null,
  avatar_hash: null,
  country: "DE",
  created_at: "2026-03-01T12:00:00Z",
  last_played_at: "2026-03-31T12:00:00Z",
  updated_at: "2026-03-31T12:00:00Z",
  steamid64,
}

const profileViews = 7

const nubRecords = [
  {
    uuid: "019d1111-1111-7111-8111-111111111111",
    id: 981200,
    player: { steamid64, display_name: "Pinned Alias" },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980200,
    map_name: "kz_alpha",
    map_tier: 4,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 42.123,
    wr_time: null,
    wr_gap: null,
    teleports: 1,
    points: 960,
    created_on: "2026-03-31T12:00:00Z",
    updated_on: "2026-03-31T12:00:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
  {
    uuid: "019d2222-2222-7222-8222-222222222222",
    id: 981201,
    player: { steamid64, display_name: "Pinned Alias" },
    steam_id: null,
    server_id: 980300,
    server_name: "Seed Server",
    map_id: 980201,
    map_name: "kz_beta",
    map_tier: 5,
    mode_id: 200,
    mode: "KZT",
    stage: 0,
    tickrate: 128,
    time: 43.5,
    wr_time: null,
    wr_gap: null,
    teleports: 2,
    points: 920,
    created_on: "2026-03-30T08:15:00Z",
    updated_on: "2026-03-30T08:15:00Z",
    updated_by: steamid64,
    replay_id: null,
    is_valid: true,
  },
]

async function installPinnedRecordRoutes(page: Page) {
  const pinnedRecords: Array<{
    id: string
    player_steamid64: string
    map_id: number
    scope: string
    type: "NUB" | "PRO"
    record: (typeof nubRecords)[number]
  }> = []
  const hiddenMapIds = new Set<number>()

  await page.addInitScript((token) => {
    localStorage.setItem("access_token", token)
  }, accessToken)

  await page.route(/\/v1\//, async (route: Route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Unhandled test route" }),
    })
  })

  await page.route(/\/v1\/admin\/servers\/access$/, async (route: Route) => {
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Forbidden" }),
    })
  })

  await page.route(/\/v1\/users\/me$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        steamid64,
        is_active: true,
        roles: [],
        created_at: "2026-03-01T12:00:00Z",
        last_visited_at: "2026-03-31T12:00:00Z",
        player: { steamid64, display_name: "Pinned Alias" },
      }),
    })
  })

  await page.route(/\/v1\/me\/settings$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        player,
        alias: { can_change: true },
        custom_id: { can_change: true },
        country: { can_change: true },
        use_wr_based_pro_completion: true,
      }),
    })
  })

  await page.route(
    /\/v1\/me\/notifications\/unread-count$/,
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ unread_count: 0 }),
      })
    },
  )

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
      body: JSON.stringify({ profile_views: profileViews }),
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
          viewer_is_self: true,
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

  await page.route(/\/v1\/maps\/wrs(\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url())
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        url.searchParams.get("type") === "PRO"
          ? []
          : [
              { map_id: 980200, time: 40, teleports: 0 },
              { map_id: 980201, time: 41, teleports: 2 },
            ],
      ),
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
          player: { steamid64, display_name: "Pinned Alias" },
          scope: "OVR",
        }),
      })
    },
  )

  await page.route(/\/v1\/records\/pb(\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url())
    const type = url.searchParams.get("type")
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(type === "PRO" ? [] : nubRecords),
    })
  })

  await page.route(/\/v1\/records\/rank(\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url())
    const uuids = url.searchParams.getAll("uuid_list")
    const data = uuids.map((uuid, index) => ({
      record_uuid: uuid,
      rank: index + 1,
      total_count: 20,
    }))
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data, count: data.length }),
    })
  })

  await page.route(/\/v1\/me\/hidden-maps(?:\/\d+)?$/, async (route: Route) => {
    const method = route.request().method()
    if (method === "POST") {
      const body = route.request().postDataJSON() as { map_id: number }
      hiddenMapIds.add(body.map_id)
    } else if (method === "DELETE") {
      const mapId = Number(route.request().url().split("/").pop())
      hiddenMapIds.delete(mapId)
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [...hiddenMapIds].map((mapId) => ({
          id: `hidden-${mapId}`,
          map_id: mapId,
          created_at: "2026-03-31T12:00:00Z",
          updated_at: "2026-03-31T12:00:00Z",
        })),
        count: hiddenMapIds.size,
      }),
    })
  })

  await page.route(
    /\/v1\/players\/[^/]+\/pinned-records(\?.*)?$/,
    async (route: Route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            data: pinnedRecords,
            count: pinnedRecords.length,
          }),
        })
        return
      }

      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON() as {
          map_id: number
          scope: string
          type: "NUB" | "PRO"
        }
        const record = nubRecords.find((entry) => entry.map_id === body.map_id)
        if (!record) {
          await route.fulfill({
            status: 404,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Pinned record target not found" }),
          })
          return
        }
        const existingIndex = pinnedRecords.findIndex(
          (entry) =>
            entry.map_id === body.map_id &&
            entry.scope === body.scope &&
            entry.type === body.type,
        )
        if (existingIndex === -1) {
          pinnedRecords.unshift({
            id: `pin-${body.map_id}-${body.type}`,
            player_steamid64: steamid64,
            map_id: body.map_id,
            scope: body.scope,
            type: body.type,
            record,
          })
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            data: pinnedRecords,
            count: pinnedRecords.length,
          }),
        })
        return
      }

      const url = new URL(route.request().url())
      const mapId = Number(url.searchParams.get("map_id"))
      const scope = url.searchParams.get("scope")
      const type = url.searchParams.get("type")
      const nextPinnedRecords = pinnedRecords.filter(
        (entry) =>
          !(
            entry.map_id === mapId &&
            entry.scope === scope &&
            entry.type === type
          ),
      )
      pinnedRecords.splice(0, pinnedRecords.length, ...nextPinnedRecords)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: pinnedRecords,
          count: pinnedRecords.length,
        }),
      })
    },
  )

  await page.route(
    /\/v1\/me\/pinned-records(?:\/\d+\/[^/]+\/[^/?]+)?(?:\?.*)?$/,
    async (route: Route) => {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON() as {
          map_id: number
          scope: string
          type: "NUB" | "PRO"
        }
        const record = nubRecords.find((entry) => entry.map_id === body.map_id)
        if (record) {
          pinnedRecords.unshift({
            id: `pin-${body.map_id}-${body.type}`,
            player_steamid64: steamid64,
            map_id: body.map_id,
            scope: body.scope,
            type: body.type,
            record,
          })
        }
      } else if (route.request().method() === "DELETE") {
        const pathParts = new URL(route.request().url()).pathname.split("/")
        const mapId = Number(pathParts.at(-3))
        const scope = pathParts.at(-2)
        const type = pathParts.at(-1)
        const nextPinnedRecords = pinnedRecords.filter(
          (entry) =>
            !(
              entry.map_id === mapId &&
              entry.scope === scope &&
              entry.type === type
            ),
        )
        pinnedRecords.splice(0, pinnedRecords.length, ...nextPinnedRecords)
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: pinnedRecords,
          count: pinnedRecords.length,
        }),
      })
    },
  )
}

test("Own profile can pin and unpin records from the records tab and home card", async ({
  page,
}) => {
  await installPinnedRecordRoutes(page)

  await page.goto(`/profile/${steamid64}/runs`)

  await page.getByTestId(`pb-record-row-${nubRecords[0].uuid}`).click({
    button: "right",
  })
  await expect(
    page.getByRole("menuitem", { name: "Pin this record" }),
  ).toBeVisible()
  await page.getByRole("menuitem", { name: "Pin this record" }).click()
  await expect(page.getByText("Record pinned")).toBeVisible()

  await page.goto(`/profile/${steamid64}`)
  await expect(page.getByText("1 of 6")).toBeVisible()
  await expect(page.getByText("kz_alpha")).toBeVisible()

  await page.getByText("kz_alpha").click({ button: "right" })
  await expect(
    page.getByRole("menuitem", { name: "Unpin this record" }),
  ).toBeVisible()
  await page.getByRole("menuitem", { name: "Unpin this record" }).click()
  await expect(page.getByText("Record unpinned")).toBeVisible()
  await expect(
    page.getByText("No pinned records found for this scope."),
  ).toBeVisible()

  await page.goto(`/profile/${steamid64}/runs`)
  await page.getByTestId(`pb-record-row-${nubRecords[0].uuid}`).click({
    button: "right",
  })
  await expect(
    page.getByRole("menuitem", { name: "Pin this record" }),
  ).toBeVisible()
})

test("Own profile can hide and restore maps from the records tab", async ({
  page,
}) => {
  await installPinnedRecordRoutes(page)
  await page.goto(`/profile/${steamid64}/runs`)

  await page.getByTestId(`pb-record-row-${nubRecords[0].uuid}`).click({
    button: "right",
  })
  await page.getByRole("menuitem", { name: "Hide this map" }).click()
  await expect(page.getByText("kz_alpha")).toHaveCount(0)
  await expect(page.getByText("kz_beta")).toBeVisible()

  await page.getByRole("button", { name: "Record page settings" }).click()
  await page
    .getByRole("menuitemcheckbox", { name: "Show hidden records" })
    .click()
  await expect(page.getByText("kz_alpha")).toBeVisible()
  await page.getByTestId(`pb-record-row-${nubRecords[0].uuid}`).click({
    button: "right",
  })
  await page.getByRole("menuitem", { name: "Unhide this map" }).click()
  await expect(page.getByText("kz_alpha")).toBeVisible()
})

test("Own profile can show and filter WR time and WR gap columns", async ({
  page,
}) => {
  await installPinnedRecordRoutes(page)
  await page.goto(`/profile/${steamid64}/runs`)

  await page.getByRole("button", { name: "Record page settings" }).click()
  await page.getByRole("menuitemcheckbox", { name: "Show WR time" }).click()
  await expect(
    page.getByRole("menuitemcheckbox", { name: "Show WR time" }),
  ).toHaveCount(0)
  await page.getByRole("button", { name: "Record page settings" }).click()
  await page.getByRole("menuitemcheckbox", { name: "Show WR gap" }).click()

  await expect
    .poll(async () => {
      const cookies = await page.context().cookies()
      return Object.fromEntries(
        cookies.map((cookie) => [cookie.name, cookie.value]),
      )
    })
    .toMatchObject({
      profile_runs_show_wr_time: "true",
      profile_runs_show_wr_gap: "true",
    })

  await page.reload()

  await expect(
    page.getByRole("columnheader", { name: "WR Time", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("columnheader", { name: "WR Gap", exact: true }),
  ).toBeVisible()
  await expect(page.getByText("40.000", { exact: true })).toBeVisible()
  await expect(page.getByText("-4.24", { exact: true })).toBeVisible()
  await expect(
    page
      .getByTestId(`pb-record-row-${nubRecords[0].uuid}`)
      .getByText("40.000", { exact: true }),
  ).toHaveClass(/text-\[#258ac7\]/)
  await expect(
    page
      .getByTestId(`pb-record-row-${nubRecords[1].uuid}`)
      .getByText("41.000", { exact: true }),
  ).toHaveClass(/text-\[#d39e00\]/)

  await page.getByLabel("Filter by wr time range").click()
  await page.getByRole("textbox", { name: "Minimum wr time" }).fill("0:41")
  await expect(page.getByText("kz_alpha")).toHaveCount(0)
  await expect(page.getByText("kz_beta")).toBeVisible()
  await page.getByRole("textbox", { name: "Minimum wr time" }).fill("")

  await page.getByLabel("Filter by wr gap range").click()
  await page.getByRole("spinbutton", { name: "Maximum wr gap" }).fill("-4.1")
  await expect(page.getByText("kz_alpha")).toBeVisible()
  await expect(page.getByText("kz_beta")).toHaveCount(0)
})
