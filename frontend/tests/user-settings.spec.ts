import { expect, type Page, test } from "@playwright/test"
import { superUserSteamid64 } from "./config"
import { randomSteamid64 } from "./utils/random"
import { logInUser } from "./utils/user"

async function stubPlayerDisplayPreviewGraphql(page: Page, steamid64: string) {
  await page.route("**/v1/**", async (route) => {
    const url = route.request().url()
    if (url.endsWith("/v1/users/me")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          steamid64,
          roles: [],
          player: {
            steamid64,
            display_name: "Display Preview",
          },
        }),
      })
      return
    }

    if (!url.endsWith("/v1/graphql")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({}),
      })
      return
    }

    const body = route.request().postDataJSON() as {
      query?: string
      variables?: Record<string, unknown>
    }
    const query = body.query ?? ""
    const variables = body.variables ?? {}

    if (query.includes("players(")) {
      const steamid64s = Array.isArray(variables.steamid64s)
        ? (variables.steamid64s as string[])
        : []
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            players: steamid64s.map((value) =>
              value === steamid64
                ? {
                    steamid64,
                    displayName: "Display Preview",
                    name: "Display Preview",
                    alias: null,
                    customId: null,
                    avatarHash: null,
                    country: "DE",
                    primaryScope: "OVR",
                    rating: 1000,
                    roles: null,
                    lastPlayedAt: null,
                  }
                : null,
            ),
          },
        }),
      })
      return
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ data: {} }),
    })
  })
}

test("My profile tab is active by default", async ({ page }) => {
  await page.goto("/settings")
  await expect(page.getByRole("tab", { name: "My profile" })).toHaveAttribute(
    "aria-selected",
    "true",
  )
  await expect(page.getByRole("tab", { name: "Danger zone" })).toHaveCount(0)
})

test("Only steam-era tabs are visible", async ({ page }) => {
  await page.goto("/settings")
  await expect(page.getByRole("tab", { name: "My profile" })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Appearance" })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Webhooks" })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Danger zone" })).toHaveCount(0)
  await expect(page.getByRole("tab", { name: "Password" })).toHaveCount(0)
})

test.describe("Profile and theme", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Profile displays steam id", async ({ page }) => {
    const steamid64 = randomSteamid64()
    await logInUser(page, steamid64)
    await page.goto("/settings")
    await expect(page.locator("p.font-mono.text-sm")).toHaveText(
      String(steamid64),
    )
  })

  test("Profile can update primary scope", async ({ page }) => {
    const steamid64 = randomSteamid64()
    await logInUser(page, steamid64)
    await page.goto("/settings")

    await expect(page.getByText("OVR", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "Edit" }).click()
    await page.getByRole("combobox").last().click()
    await page.getByText("VNL", { exact: true }).click()
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("Profile settings updated.")).toBeVisible()
    await expect(page.getByText("VNL", { exact: true })).toBeVisible()
  })

  test("Player can generate, copy, and replace a QQ binding code", async ({
    page,
  }) => {
    const steamid64 = randomSteamid64()
    const responses = [
      {
        code: "KZTOP4rj4edqq85nr0jjlwm5zw2l4rjownqfxztl9qtym3ns-2r83jg4x7jv88qn5xkqlh0412",
        expires_at: "2026-06-26T12:10:00Z",
      },
      {
        code: "KZTOP4rj4edqq85nr0jjlwm5zw2l4rjownqfxztl9qtym3nt-18ra54djs9sbj3rsk5y2iu0hh",
        expires_at: "2026-06-26T12:20:00Z",
      },
    ]
    let requestCount = 0

    await logInUser(page, steamid64)
    await page.addInitScript(() => {
      Object.defineProperty(window, "__copiedText", {
        configurable: true,
        writable: true,
        value: "",
      })
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: async (text: string) => {
            ;(window as typeof window & { __copiedText: string }).__copiedText =
              text
          },
        },
      })
    })
    await page.route(/\/v1\/me\/qq-binding-code$/, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback()
        return
      }

      const response = responses[Math.min(requestCount, responses.length - 1)]
      requestCount += 1
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(response),
      })
    })

    await page.goto("/settings/binding-code")

    await page.getByRole("button", { name: "Generate QQ Binding Code" }).click()
    await expect(page.getByTestId("settings-qq-binding-code")).toHaveText(
      responses[0].code,
    )
    await page.getByTestId("settings-qq-binding-copy-button").click()
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            (window as typeof window & { __copiedText: string }).__copiedText,
        ),
      )
      .toBe(responses[0].code)

    await page.getByRole("button", { name: "Generate QQ Binding Code" }).click()
    await expect(page.getByTestId("settings-qq-binding-code")).toHaveText(
      responses[1].code,
    )
    await expect(
      page.getByText("Send /bind <code> to the QQ bot."),
    ).toHaveCount(0)
  })

  test("QQ binding code generation shows backend errors", async ({ page }) => {
    const steamid64 = randomSteamid64()
    await logInUser(page, steamid64)
    await page.route(/\/v1\/me\/qq-binding-code$/, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback()
        return
      }

      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "QQ binding code generation is not configured",
        }),
      })
    })

    await page.goto("/settings/profile")
    await page.getByRole("button", { name: "Generate QQ Binding Code" }).click()

    await expect(
      page.getByText("QQ binding code generation is not configured"),
    ).toBeVisible()
  })

  test("Appearance can configure player display preferences", async ({
    page,
  }) => {
    const steamid64 = randomSteamid64()
    const accessToken = [
      "e30",
      Buffer.from(JSON.stringify({ sub: String(steamid64) })).toString(
        "base64url",
      ),
      "signature",
    ].join(".")
    await stubPlayerDisplayPreviewGraphql(page, String(steamid64))
    await page.goto(`/auth/callback#access_token=${accessToken}`)

    await page.goto("/settings/appearance")

    await expect(page.getByText("Player Display")).toBeVisible()
    const preview = page.getByTestId("appearance-player-display-preview")
    await expect(preview.getByText("Display Preview")).toBeVisible()
    await expect(page.getByTestId(`country-flag-${steamid64}`)).toBeVisible()
    await expect(page.getByTestId(`rating-icon-${steamid64}`)).toBeVisible()

    await page.getByTestId("appearance-player-country-flag-switch").click()
    await expect(page.getByTestId(`country-flag-${steamid64}`)).toHaveCount(0)
    await expect
      .poll(() =>
        page.evaluate(() =>
          JSON.parse(
            localStorage.getItem("gokz-player-display-appearance") || "{}",
          ),
        ),
      )
      .toMatchObject({ showCountryFlag: false })

    await page.getByTestId("appearance-player-rating-icon-switch").click()
    await expect(page.getByTestId(`rating-icon-${steamid64}`)).toHaveCount(0)
    await expect
      .poll(() =>
        page.evaluate(() =>
          JSON.parse(
            localStorage.getItem("gokz-player-display-appearance") || "{}",
          ),
        ),
      )
      .toMatchObject({ showRatingIcon: false })

    await page.getByTestId("appearance-player-rating-scope-select").click()
    await page
      .getByTestId("appearance-player-rating-scope-option-global")
      .click()
    await expect
      .poll(() =>
        page.evaluate(() =>
          JSON.parse(
            localStorage.getItem("gokz-player-display-appearance") || "{}",
          ),
        ),
      )
      .toMatchObject({ ratingIconScope: "global" })
  })

  test("Social links tab can add and delete a link", async ({ page }) => {
    const steamid64 = randomSteamid64()
    let links: unknown[] = []
    await logInUser(page, steamid64)
    await page.route(
      new RegExp(
        `/v1/player-social-links/(players/${steamid64}|me/social-links)$`,
      ),
      async (route) => {
        if (route.request().method() === "POST") {
          links = [
            {
              id: "019e0000-0000-7000-8000-000000000201",
              player_steamid64: String(steamid64),
              platform: "x",
              account_identifier: "settings_user",
              verified: false,
              url: "https://x.com/settings_user",
              created_at: "2026-04-01T00:00:00Z",
              updated_at: "2026-04-01T00:00:00Z",
            },
          ]
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )
    await page.route(
      /\/v1\/player-social-links\/me\/social-links\/[^/]+$/,
      async (route) => {
        if (route.request().method() === "DELETE") {
          links = []
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )

    await page.goto("/settings")
    await page.getByRole("tab", { name: "Social links" }).click()
    await page.getByRole("button", { name: "Add" }).click()
    await page
      .getByRole("textbox", { name: "Social profile URL" })
      .fill("https://x.com/settings_user")
    await page.getByRole("button", { name: "Add link" }).click()

    await expect(page.getByText("settings_user")).toBeVisible()
    await expect(page.getByText("Unverified")).toBeVisible()

    await page.getByRole("button", { name: "Delete X link" }).click()
    await expect(page.getByText("No social links added yet.")).toBeVisible()
  })

  test("Twitch quick link opens a popup and success refreshes the list", async ({
    page,
  }) => {
    const steamid64 = randomSteamid64()
    let links: unknown[] = []
    await logInUser(page, steamid64)
    await page.route(
      new RegExp(`/v1/player-social-links/players/${steamid64}$`),
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )
    await page.route(
      /\/v1\/player-social-links\/me\/social-links\/twitch\/connection-requests$/,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            authorization_url:
              "https://id.twitch.tv/oauth2/authorize?client_id=test&state=test",
          }),
        })
      },
    )

    await page.goto("/settings")
    await page.getByRole("tab", { name: "Social links" }).click()
    await page.getByRole("button", { name: "Add" }).click()

    const popupPromise = page.waitForEvent("popup")
    await page.getByRole("button", { name: "Twitch" }).click()
    await popupPromise

    links = [
      {
        id: "019e0000-0000-7000-8000-000000000401",
        player_steamid64: String(steamid64),
        platform: "twitch",
        account_identifier: "linkedstreamer",
        verified: true,
        url: "https://www.twitch.tv/linkedstreamer",
        created_at: "2026-04-01T00:00:00Z",
        updated_at: "2026-04-01T00:00:00Z",
      },
    ]

    await page.evaluate(() => {
      window.postMessage(
        {
          type: "twitch-social-link-verification",
          status: "success",
        },
        window.location.origin,
      )
    })

    await expect(page.getByText("Twitch account linked")).toBeVisible()
    await expect(page.getByText("linkedstreamer")).toBeVisible()
  })

  test("YouTube quick link opens a popup and success refreshes the list", async ({
    page,
  }) => {
    const steamid64 = randomSteamid64()
    let links: unknown[] = []
    await logInUser(page, steamid64)
    await page.route(
      new RegExp(`/v1/player-social-links/players/${steamid64}$`),
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )
    await page.route(
      /\/v1\/player-social-links\/me\/social-links\/youtube\/connection-requests$/,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            authorization_url:
              "https://accounts.google.com/o/oauth2/v2/auth?client_id=test&state=test",
          }),
        })
      },
    )

    await page.goto("/settings")
    await page.getByRole("tab", { name: "Social links" }).click()
    await page.getByRole("button", { name: "Add" }).click()

    const popupPromise = page.waitForEvent("popup")
    await page.getByRole("button", { name: "YouTube" }).click()
    await popupPromise

    links = [
      {
        id: "019e0000-0000-7000-8000-000000000402",
        player_steamid64: String(steamid64),
        platform: "youtube",
        account_identifier: "channel/UC12345678901234567890AB",
        verified: true,
        url: "https://www.youtube.com/channel/UC12345678901234567890AB",
        created_at: "2026-04-01T00:00:00Z",
        updated_at: "2026-04-01T00:00:00Z",
      },
    ]

    await page.evaluate(() => {
      window.postMessage(
        {
          type: "youtube-social-link-verification",
          status: "success",
        },
        window.location.origin,
      )
    })

    await expect(page.getByText("YouTube channel linked")).toBeVisible()
    await expect(
      page.getByText("channel/UC12345678901234567890AB"),
    ).toBeVisible()
  })

  test("Social links tab honors URL state and can confirm Twitch verification mismatch", async ({
    page,
  }) => {
    const steamid64 = randomSteamid64()
    let links = [
      {
        id: "019e0000-0000-7000-8000-000000000301",
        player_steamid64: String(steamid64),
        platform: "twitch",
        account_identifier: "oldstreamer",
        verified: false,
        url: "https://www.twitch.tv/oldstreamer",
        created_at: "2026-04-01T00:00:00Z",
        updated_at: "2026-04-01T00:00:00Z",
      },
      {
        id: "019e0000-0000-7000-8000-000000000302",
        player_steamid64: String(steamid64),
        platform: "github",
        account_identifier: "settings_user",
        verified: false,
        url: "https://github.com/settings_user",
        created_at: "2026-04-01T00:00:00Z",
        updated_at: "2026-04-01T00:00:00Z",
      },
    ]

    await logInUser(page, steamid64)
    await page.route(
      new RegExp(`/v1/player-social-links/players/${steamid64}$`),
      async (route) => {
        await route.fulfill({
          status: route.request().method() === "POST" ? 200 : 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )
    await page.route(
      /\/v1\/player-social-links\/me\/social-links\/019e0000-0000-7000-8000-000000000301\/twitch-verification-confirmations$/,
      async (route) => {
        links = [
          {
            ...links[0],
            account_identifier: "verifiedstreamer",
            verified: true,
            url: "https://www.twitch.tv/verifiedstreamer",
          },
          links[1],
        ]
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )

    await page.goto(
      "/settings?tab=social-links&twitchVerification=mismatch&linkId=019e0000-0000-7000-8000-000000000301&currentAccount=oldstreamer&authenticatedAccount=verifiedstreamer&authenticatedDisplayName=VerifiedStreamer&pendingToken=test-pending-token",
    )

    await expect(page).toHaveURL(/\/settings\/social-links(?:\?|$)/)
    await expect(
      page.getByRole("button", { name: "Verify" }).first(),
    ).toBeEnabled()
    await expect(page.getByRole("button", { name: "Verify" })).toHaveCount(1)
    await expect(page.getByText("Confirm Twitch account")).toBeVisible()
    await expect(page.getByText(/^VerifiedStreamer$/)).toBeVisible()
    await expect(
      page.getByLabel("Confirm Twitch account").getByText(/^oldstreamer$/),
    ).toBeVisible()

    await page.getByRole("button", { name: "Replace and verify" }).click()

    await expect(page.getByText("Confirm Twitch account")).toHaveCount(0)
    await expect(page.getByText(/^verifiedstreamer$/)).toBeVisible()
    await expect(page.getByText("Unverified")).toHaveCount(1)
    await expect(page.getByText("oldstreamer")).toHaveCount(0)
  })

  test("Social links tab can confirm YouTube verification mismatch", async ({
    page,
  }) => {
    const steamid64 = randomSteamid64()
    let links = [
      {
        id: "019e0000-0000-7000-8000-000000000501",
        player_steamid64: String(steamid64),
        platform: "youtube",
        account_identifier: "@oldchannel",
        verified: false,
        url: "https://www.youtube.com/@oldchannel",
        created_at: "2026-04-01T00:00:00Z",
        updated_at: "2026-04-01T00:00:00Z",
      },
    ]

    await logInUser(page, steamid64)
    await page.route(
      new RegExp(`/v1/player-social-links/players/${steamid64}$`),
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )
    await page.route(
      /\/v1\/player-social-links\/me\/social-links\/019e0000-0000-7000-8000-000000000501\/youtube-verification-confirmations$/,
      async (route) => {
        links = [
          {
            ...links[0],
            account_identifier: "channel/UC12345678901234567890AB",
            verified: true,
            url: "https://www.youtube.com/channel/UC12345678901234567890AB",
          },
        ]
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: links, count: links.length }),
        })
      },
    )

    await page.goto(
      "/settings?tab=social-links&youtubeVerification=mismatch&linkId=019e0000-0000-7000-8000-000000000501&currentAccount=%40oldchannel&authenticatedAccount=channel%2FUC12345678901234567890AB&authenticatedDisplayName=Verified%20Channel&pendingToken=test-pending-token",
    )

    await expect(page.getByText("Confirm YouTube channel")).toBeVisible()
    await expect(page.getByText(/^Verified Channel$/)).toBeVisible()
    await expect(
      page.getByLabel("Confirm YouTube channel").getByText(/^@oldchannel$/),
    ).toBeVisible()

    await page.getByRole("button", { name: "Replace and verify" }).click()

    await expect(page.getByText("Confirm YouTube channel")).toHaveCount(0)
    await expect(
      page.getByText("channel/UC12345678901234567890AB"),
    ).toBeVisible()
    await expect(page.getByText("Unverified")).toHaveCount(0)
  })

  test("Webhooks tab can add, toggle, test, edit, and delete a webhook", async ({
    page,
  }) => {
    let webhooks = [] as Array<{
      id: string
      provider: "discord"
      url: string
      enabled: boolean
      last_used_at: string | null
      created_at: string
      updated_at: string
    }>

    await logInUser(page, randomSteamid64())
    await page.route(/\/v1\/players\/me\/webhooks$/, async (route) => {
      if (route.request().method() === "POST") {
        const requestBody = route.request().postDataJSON() as { url: string }
        webhooks = [
          {
            id: "019e0000-0000-7000-8000-000000000401",
            provider: "discord",
            url: requestBody.url,
            enabled: true,
            last_used_at: null,
            created_at: "2026-04-01T00:00:00Z",
            updated_at: "2026-04-01T00:00:00Z",
          },
        ]
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: webhooks, count: webhooks.length }),
      })
    })
    await page.route(/\/v1\/players\/me\/webhooks\/[^/]+$/, async (route) => {
      const webhookId = route.request().url().split("/").pop() ?? ""
      if (route.request().method() === "PATCH") {
        const requestBody = route.request().postDataJSON() as {
          url?: string
          enabled?: boolean
        }
        webhooks = webhooks.map((webhook) =>
          webhook.id === webhookId
            ? {
                ...webhook,
                url: requestBody.url ?? webhook.url,
                enabled: requestBody.enabled ?? webhook.enabled,
                updated_at: "2026-04-02T00:00:00Z",
              }
            : webhook,
        )
      }
      if (route.request().method() === "DELETE") {
        webhooks = webhooks.filter((webhook) => webhook.id !== webhookId)
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: webhooks, count: webhooks.length }),
      })
    })
    await page.route(
      /\/v1\/players\/me\/webhooks\/[^/]+\/test$/,
      async (route) => {
        const parts = route.request().url().split("/")
        const webhookId = parts[parts.length - 2] ?? ""
        const updatedWebhook = webhooks.find(
          (webhook) => webhook.id === webhookId,
        )
        if (updatedWebhook) {
          updatedWebhook.last_used_at = "2026-04-03T00:00:00Z"
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(updatedWebhook),
        })
      },
    )

    await page.goto("/settings?tab=webhooks")
    await expect(page).toHaveURL(/\/settings\/webhooks$/)

    await page.getByRole("button", { name: /\+?\s*Add/ }).click()
    await page
      .getByRole("textbox", { name: "Discord webhook URL" })
      .fill(
        "https://discord.com/api/webhooks/123456789012345678/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      )
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("Webhook added")).toBeVisible()
    await expect(
      page.getByText("Discord webhook • aaaa...", { exact: true }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Send test" }).click()
    await expect(page.getByText("Webhook test sent")).toBeVisible()
    await page.getByRole("dialog").locator('[data-slot="dialog-close"]').click()
    await expect(page.getByText("Last used:")).toBeVisible()

    await page.getByRole("switch").click()
    await expect(page.getByText("Webhook updated").first()).toBeVisible()
    await expect(page.getByText("Disabled")).toBeVisible()

    await page.getByRole("button", { name: "Edit Discord webhook" }).click()
    await page.getByRole("button", { name: "Send test" }).click()
    await expect(page.getByText("Webhook test sent")).toBeVisible()
    await page
      .getByRole("textbox", { name: "Edit Discord webhook URL" })
      .fill(
        "https://discord.com/api/webhooks/987654321098765432/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      )
    await page.getByRole("button", { name: "Save" }).click()
    await expect(page.getByText("Webhook updated").first()).toBeVisible()
    await expect(
      page.getByText("Discord webhook • bbbb...", { exact: true }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Delete Discord webhook" }).click()
    await expect(page.getByText("Webhook deleted")).toBeVisible()
    await expect(page.getByText("No webhooks added yet.")).toBeVisible()
  })

  test("Theme selected in appearance settings is preserved across sessions", async ({
    page,
  }) => {
    await logInUser(page, superUserSteamid64, { roles: ["superuser"] })
    await page.goto("/settings")

    await page.getByRole("tab", { name: "Appearance" }).click()
    await page.getByTestId("appearance-theme-select").click()
    await page.getByTestId("appearance-theme-option-light").click()
    await expect(page.locator("html")).toHaveClass(/light/)

    await page.evaluate(() => {
      localStorage.removeItem("access_token")
    })
    await logInUser(page, superUserSteamid64, { roles: ["superuser"] })
    await expect(page.locator("html")).toHaveClass(/light/)
  })

  test("Datetime settings default to iso-like, show previews, and support 12h", async ({
    page,
  }) => {
    await logInUser(page, superUserSteamid64, { roles: ["superuser"] })
    await page.goto("/settings")

    await page.getByRole("tab", { name: "Appearance" }).click()
    await expect(
      page.getByTestId("appearance-datetime-preset-select"),
    ).toContainText("ISO-like")
    await expect(
      page.getByTestId("appearance-datetime-preview-default"),
    ).toContainText("2026-03-22 14:05")
    await expect(
      page.getByTestId("appearance-datetime-preview-seconds"),
    ).toContainText("2026-03-22 14:05:09")

    await page.getByTestId("appearance-datetime-preset-select").click()
    await expect(
      page.getByTestId("appearance-datetime-preset-option-iso"),
    ).toContainText("2026-03-22 14:05")
    await expect(
      page.getByTestId("appearance-datetime-preset-option-us"),
    ).toContainText("03/22/2026")
    await expect(
      page.getByTestId("appearance-datetime-preset-option-euro"),
    ).toContainText("22/03/2026")
    await expect(
      page.getByTestId("appearance-datetime-preset-option-long"),
    ).toContainText("March")
    await page.getByTestId("appearance-datetime-preset-option-iso").click()

    await page.getByTestId("appearance-hour-cycle-select").click()
    await expect(
      page.getByTestId("appearance-hour-cycle-option-24h"),
    ).toContainText("2026-03-22 14:05")
    await expect(
      page.getByTestId("appearance-hour-cycle-option-12h"),
    ).toContainText("2026-03-22 02:05 PM")
    await page.getByTestId("appearance-hour-cycle-option-12h").click()

    await expect(
      page.getByTestId("appearance-hour-cycle-select"),
    ).toContainText("12-hour")
    await expect(
      page.getByTestId("appearance-datetime-preview-default"),
    ).toContainText("2026-03-22 02:05 PM")
    await expect(
      page.getByTestId("appearance-datetime-preview-seconds"),
    ).toContainText("2026-03-22 02:05:09 PM")
    await expect(
      page.getByTestId("appearance-datetime-preview-relative"),
    ).toContainText("1 hour ago")

    await page.reload()
    await page.getByRole("tab", { name: "Appearance" }).click()
    await expect(
      page.getByTestId("appearance-datetime-preset-select"),
    ).toContainText("ISO-like")
    await expect(
      page.getByTestId("appearance-hour-cycle-select"),
    ).toContainText("12-hour")

    await page.goto("/admin/players")
    await expect(page.getByRole("heading", { name: "Players" })).toBeVisible()
    await expect(
      page.getByText(/2026-\d{2}-\d{2} \d{2}:\d{2} [AP]M/).first(),
    ).toBeVisible()
    await expect(
      page.getByText(/2026-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [AP]M/),
    ).toHaveCount(0)
  })
})
