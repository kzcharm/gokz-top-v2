import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })
const steamid = "76561198000000001"
const recordUuid = "019e1111-1111-7111-8111-111111111111"
const map = {
  id: 980200,
  name: "kz_slide_arid",
  validated: true,
  tiers: { OVR: 4, KZT: 4, SKZ: 4, VNL: 4 },
  bonus_count: 0,
  authors: [],
  no_steamid_names: [],
  workshop_id: null,
  created_on: "2026-03-01T08:00:00Z",
  updated_on: "2026-03-01T08:00:00Z",
}
const record = {
  uuid: recordUuid,
  id: 980900,
  player: { steamid64: steamid, display_name: "Reported Runner" },
  server_id: 980300,
  server_name: "Test Server",
  map_id: map.id,
  map_name: map.name,
  map_tier: 4,
  mode_id: 200,
  mode: "KZT",
  stage: 0,
  tickrate: 128,
  time: 41.123,
  teleports: 0,
  points: 1000,
  is_valid: true,
  created_on: "2026-03-01T08:00:00Z",
  updated_on: "2026-03-01T08:00:00Z",
  is_replay_available: false,
}

const previewData = {
  count: 3,
  preview_token: "a".repeat(64),
  players: [
    {
      player: record.player,
      records: [
        {
          uuid: "019e1111-1111-7111-8111-333333333333",
          time: 30.123,
          mode: "KZT",
          teleports: 0,
          server_name: "Preview Server",
          created_on: record.created_on,
        },
        {
          uuid: "019e1111-1111-7111-8111-444444444444",
          time: 32.25,
          mode: "NKZ",
          teleports: 0,
          server_name: "Preview Server",
          created_on: record.created_on,
        },
      ],
    },
    {
      player: { steamid64: "76561198000000002", display_name: "Second Runner" },
      records: [
        {
          uuid: "019e1111-1111-7111-8111-555555555555",
          time: 39.125,
          mode: "KZT",
          teleports: 0,
          server_name: "Other Server",
          created_on: record.created_on,
        },
      ],
    },
  ],
}

async function installRoutes(page: Page, admin: boolean) {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "test.token.signature")
    localStorage.setItem("i18nextLng", "en")
  })
  let leaderboardReads = 0
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = { data: [], count: 0 }
    if (path === "/v1/users/me")
      body = {
        steamid64: steamid,
        is_active: true,
        roles: admin ? ["admin"] : [],
        player: { ...record.player, display_name: "Moderation Admin" },
      }
    else if (path.includes("/admin/servers/access")) {
      await route.fulfill({ status: 403, json: { detail: "Forbidden" } })
      return
    } else if (path === "/v1/graphql") body = { data: {} }
    else if (path === "/v1/me/notifications/unread-count")
      body = { unread_count: 0 }
    else if (path === "/v1/records/bulk-delete-faster/preview")
      body = previewData
    else if (path === "/v1/maps") body = [map]
    else if (path === "/v1/maps/name/kz_slide_arid") body = map
    else if (path === "/v1/maps/980200/leaderboard") {
      leaderboardReads++
      body = {
        data: [record],
        count: 1,
        unique_nub_finishes: 1,
        unique_pro_finishes: 1,
        current_user_rank: null,
        current_user_steamid64: null,
      }
    } else if (path === "/v1/records/pb" || path === "/v1/maps/wrs") body = []
    else if (path.endsWith("/stats"))
      body = { nub_wr_gap_distribution: [], pro_wr_gap_distribution: [] }
    await route.fulfill({ json: body })
  })
  return { reads: () => leaderboardReads }
}

async function openDeleteDialog(page: Page) {
  await page
    .locator("tr")
    .filter({ hasText: "Reported Runner" })
    .click({ button: "right" })
  await page.getByRole("menuitem", { name: "Delete faster records…" }).click()
  return page.getByRole("dialog", { name: "Delete faster records?" })
}

test("admin confirms cutoff, cancels, retries errors and refreshes after deletion", async ({
  page,
}) => {
  const state = await installRoutes(page, true)
  const requests: unknown[] = []
  let fail = true
  let release: (() => void) | undefined
  await page.route("**/v1/records/bulk-delete-faster", async (route) => {
    requests.push(route.request().postDataJSON())
    if (fail) {
      await route.fulfill({ status: 500, json: { detail: "Failed" } })
      return
    }
    await new Promise<void>((resolve) => {
      release = resolve
    })
    await route.fulfill({ json: { count: 3 } })
  })
  await page.goto("/maps/kz_slide_arid/maptop?scope=KZT&type=PRO")
  await expect(page.getByText("Reported Runner", { exact: true })).toBeVisible()
  await page
    .locator("tr")
    .filter({ hasText: "Reported Runner" })
    .click({ button: "right" })
  await expect(
    page.getByRole("menuitem", { name: "Delete faster records…" }),
  ).toHaveCount(0)
  await page.keyboard.press("Escape")
  await page.getByRole("button", { name: "Admin mode", exact: true }).click()
  let dialog = await openDeleteDialog(page)
  await expect(dialog).toContainText("KZT PRO")
  await expect(dialog).toContainText("41.123")
  await expect(dialog).toContainText("Historical runs are included")
  await expect(dialog).toContainText(
    "Equal times and the selected run are preserved",
  )
  const preview = dialog.getByRole("region", { name: "Records to delete" })
  await expect(preview).toContainText("3 runs · 2 players")
  await expect(preview.locator("details")).toHaveCount(2)
  const player = preview
    .locator("details")
    .filter({ hasText: "Reported Runner" })
  await expect(player.getByText("2 runs", { exact: true })).toBeVisible()
  await expect(
    player.getByRole("link", { name: "Reported Runner", exact: false }),
  ).toHaveAttribute("href", `/profile/${steamid}`)
  await expect(player.locator("tbody tr")).toHaveCount(0)
  await player.locator("summary > svg").click()
  await expect(player.locator("tbody tr")).toHaveCount(2)
  await expect(player.getByText("0:30.123", { exact: true })).toBeVisible()
  await expect(player.getByText("NKZ", { exact: true })).toBeVisible()
  await expect(player.locator("tbody tr").first()).toContainText(
    "Preview Server",
  )
  await dialog.screenshot({
    path: "../.temp/record-moderation/preview-confirmation.png",
  })
  await player.locator("summary > svg").click()
  await expect(player.locator("tbody tr")).toHaveCount(0)
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
  expect(requests).toHaveLength(0)
  dialog = await openDeleteDialog(page)
  await dialog
    .getByRole("button", { name: "Delete faster records", exact: true })
    .click()
  await expect(
    page.getByText("Could not delete faster records. Please try again."),
  ).toBeVisible()
  await expect(dialog).toBeVisible()
  expect(requests).toEqual([
    {
      record_uuid: recordUuid,
      scope: "KZT",
      type: "PRO",
      preview_token: previewData.preview_token,
    },
  ])
  fail = false
  const before = state.reads()
  await dialog
    .getByRole("button", { name: "Delete faster records", exact: true })
    .click()
  await expect(
    dialog.getByRole("button", { name: "Delete faster records", exact: true }),
  ).toBeDisabled()
  await expect.poll(() => !!release).toBe(true)
  expect(requests).toHaveLength(2)
  release?.()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText("Deleted 3 records.")).toBeVisible()
  await expect.poll(state.reads).toBeGreaterThan(before)
  await page.screenshot({
    path: "../.temp/record-moderation/maptop.png",
    fullPage: true,
  })
})

test("ordinary users cannot access bulk record moderation", async ({
  page,
}) => {
  await installRoutes(page, false)
  await page.goto("/maps/kz_slide_arid/maptop")
  await page
    .locator("tr")
    .filter({ hasText: "Reported Runner" })
    .click({ button: "right" })
  await expect(
    page.getByRole("menuitem", { name: "Report", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("menuitem", { name: "Delete faster records…" }),
  ).toHaveCount(0)
  await expect(
    page.getByRole("button", { name: "Admin mode", exact: true }),
  ).toHaveCount(0)
})

test("reporters see invalidated record context and can mark the notification read", async ({
  page,
}) => {
  await installRoutes(page, false)
  let read = false
  const notification = () => ({
    id: "019e1111-1111-7111-8111-222222222222",
    type: "reported_record_invalidated",
    created_at: "2026-10-21T10:00:00Z",
    read_at: read ? "2026-10-21T11:00:00Z" : null,
    target_url: `/profile/${steamid}/records`,
    target_player: record.player,
    target_player_steamid64: steamid,
    map_id: map.id,
    map_name: map.name,
    scope: "KZT",
    record_type: "PRO",
    new_record_uuid: recordUuid,
    new_record_time: 41.123,
  })
  await page.route("**/v1/me/notifications/unread-count", (route) =>
    route.fulfill({ json: { unread_count: read ? 0 : 1 } }),
  )
  await page.route(/\/v1\/me\/notifications(?:\?.*)?$/, (route) =>
    route.fulfill({ json: { data: [notification()], count: 1 } }),
  )
  await page.route("**/v1/me/notifications/*/read", async (route) => {
    read = true
    await route.fulfill({ json: notification() })
  })
  await page.goto("/settings/notifications")
  await expect(
    page.getByText("A record you reported was invalidated."),
  ).toBeVisible()
  await expect(page.getByText("Reported Runner", { exact: true })).toBeVisible()
  await expect(
    page.getByRole("link", { name: "kz_slide_arid", exact: true }),
  ).toHaveAttribute("href", "/maps/kz_slide_arid/maptop?scope=KZT&type=PRO")
  await expect(page.getByText(/KZT - PRO - .*41\.123/)).toBeVisible()
  await page
    .getByRole("button", {
      name: "A record you reported was invalidated.",
      exact: true,
    })
    .click()
  await expect.poll(() => read).toBe(true)
  await expect(page.getByText("Unread", { exact: true })).toHaveCount(0)
})

test("bulk deletion clamps a leaderboard page that no longer exists", async ({
  page,
}) => {
  await installRoutes(page, true)
  let deleted = false
  const offsets: number[] = []
  await page.route("**/v1/maps/980200/leaderboard?*", async (route) => {
    const offset = Number(
      new URL(route.request().url()).searchParams.get("offset") ?? 0,
    )
    offsets.push(offset)
    await route.fulfill({
      json: {
        data: deleted && offset > 0 ? [] : [record],
        count: deleted ? 1 : 21,
        unique_nub_finishes: 21,
        unique_pro_finishes: 21,
        current_user_rank: null,
        current_user_steamid64: null,
      },
    })
  })
  await page.route("**/v1/records/bulk-delete-faster", async (route) => {
    deleted = true
    await route.fulfill({ json: { count: 20 } })
  })
  await page.goto("/maps/kz_slide_arid/maptop?scope=KZT&type=PRO")
  await page.getByRole("button", { name: "Admin mode", exact: true }).click()
  await page
    .getByRole("button", { name: "Go to next page", exact: true })
    .click()
  await expect.poll(() => offsets.includes(20)).toBe(true)
  const dialog = await openDeleteDialog(page)
  await dialog
    .getByRole("button", { name: "Delete faster records", exact: true })
    .click()
  await expect(dialog).not.toBeVisible()
  await expect(
    page.getByRole("spinbutton", { name: "Current page, 1 total pages" }),
  ).toHaveValue("1")
  await expect(
    page.getByRole("button", { name: "Go to previous page", exact: true }),
  ).toBeDisabled()
  await expect(
    page.locator("tr").filter({ hasText: "Reported Runner" }),
  ).toBeVisible()
})

test("preview loading and errors block deletion until a successful retry", async ({
  page,
}) => {
  await installRoutes(page, true)
  let release: (() => void) | undefined
  let calls = 0
  await page.route(
    "**/v1/records/bulk-delete-faster/preview",
    async (route) => {
      calls++
      if (calls === 1) {
        await new Promise<void>((resolve) => {
          release = resolve
        })
        await route.fulfill({ status: 500, json: { detail: "Preview failed" } })
      } else await route.fulfill({ json: previewData })
    },
  )
  await page.goto("/maps/kz_slide_arid/maptop")
  await page.getByRole("button", { name: "Admin mode", exact: true }).click()
  const dialog = await openDeleteDialog(page)
  const confirm = dialog.getByRole("button", {
    name: "Delete faster records",
    exact: true,
  })
  await expect(
    dialog.getByRole("status", { name: "Loading affected records" }),
  ).toBeVisible()
  await expect(confirm).toBeDisabled()
  await expect.poll(() => !!release).toBe(true)
  release?.()
  await expect(
    dialog.getByText("Could not load the record preview."),
  ).toBeVisible()
  await expect(confirm).toBeDisabled()
  await dialog.getByRole("button", { name: "Retry", exact: true }).click()
  await expect(
    dialog.getByRole("region", { name: "Records to delete" }),
  ).toBeVisible()
  await expect(confirm).toBeEnabled()
})

test("an empty preview keeps deletion disabled", async ({ page }) => {
  await installRoutes(page, true)
  await page.route("**/v1/records/bulk-delete-faster/preview", (route) =>
    route.fulfill({
      json: {
        count: 0,
        players: [],
        preview_token: previewData.preview_token,
      },
    }),
  )
  await page.goto("/maps/kz_slide_arid/maptop")
  await page.getByRole("button", { name: "Admin mode", exact: true }).click()
  const dialog = await openDeleteDialog(page)
  await expect(dialog.getByText("No faster records to delete.")).toBeVisible()
  await expect(
    dialog.getByRole("button", { name: "Delete faster records", exact: true }),
  ).toBeDisabled()
})

test("changed records refresh the preview and require another confirmation", async ({
  page,
}) => {
  await installRoutes(page, true)
  let changed = false
  const tokens: string[] = []
  await page.route("**/v1/records/bulk-delete-faster/preview", (route) =>
    route.fulfill({
      json: {
        ...previewData,
        preview_token: changed ? "b".repeat(64) : previewData.preview_token,
      },
    }),
  )
  await page.route("**/v1/records/bulk-delete-faster", async (route) => {
    tokens.push(route.request().postDataJSON().preview_token)
    if (!changed) {
      changed = true
      await route.fulfill({ status: 409, json: { detail: "Records changed" } })
    } else await route.fulfill({ json: { count: 3 } })
  })
  await page.goto("/maps/kz_slide_arid/maptop")
  await page.getByRole("button", { name: "Admin mode", exact: true }).click()
  const dialog = await openDeleteDialog(page)
  const confirm = dialog.getByRole("button", {
    name: "Delete faster records",
    exact: true,
  })
  await expect(confirm).toBeEnabled()
  await confirm.click()
  await expect(
    page.getByText(
      "Records have changed. Review the updated preview before deleting.",
    ),
  ).toBeVisible()
  await expect(confirm).toBeEnabled()
  expect(tokens).toHaveLength(1)
  await confirm.click()
  await expect(dialog).not.toBeVisible()
  expect(tokens).toEqual([previewData.preview_token, "b".repeat(64)])
})
