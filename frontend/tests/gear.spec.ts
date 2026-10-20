import { expect, type Page, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })
const product = {
  id: "019d1111-1111-7111-8111-111111111111",
  category: "mouse",
  brand: "Logitech",
  model: "PRO X SUPERLIGHT 2",
  community_added: false,
}
const blank = {
  hardware: [],
  game_settings: { mouse_dpi: null, sensitivity: null, edpi: null },
}

async function mock(page: Page, signedIn = true) {
  await page.addInitScript((authenticated) => {
    localStorage.setItem("i18nextLng", "en")
    if (authenticated) localStorage.setItem("access_token", "test-token")
  }, signedIn)
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === "/v1/users/me")
      return route.fulfill({
        json: {
          steamid64: "76561198000000001",
          is_active: true,
          roles: [],
          player: {
            steamid64: "76561198000000001",
            display_name: "Gear Tester",
          },
        },
      })
    if (url.pathname === "/v1/me/setup") return route.fulfill({ json: blank })
    if (url.pathname === "/v1/products/brands")
      return route.fulfill({ json: ["Logitech", "Razer"] })
    if (url.pathname === "/v1/products")
      return route.fulfill({ json: { data: [product], count: 1 } })
    if (url.pathname === "/v1/leaderboards/gear")
      return route.fulfill({
        json: {
          data: [{ rank: 1, product, players: 12, share: 60 }],
          count: 1,
          participants: 20,
        },
      })
    if (url.pathname.endsWith("unread-count"))
      return route.fulfill({ json: { count: 0, unread_count: 0 } })
    return route.fulfill({ json: { data: [], count: 0 } })
  })
}

test("setup calculates eDPI, saves a selected product, and retains settings after reload", async ({
  page,
}) => {
  await mock(page)
  let saved: any = blank
  await page.route("**/v1/me/setup", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON()
      saved = {
        ...body,
        hardware: body.hardware.map((item: object) => ({ ...item, product })),
        game_settings: { ...body.game_settings, edpi: "1000" },
      }
    }
    return route.fulfill({ json: saved })
  })
  await page.goto("/settings/setup")
  await page
    .getByRole("combobox", { name: "Mouse", exact: true })
    .fill("Superlight")
  await page
    .getByRole("option", { name: "Logitech PRO X SUPERLIGHT 2" })
    .click()
  await expect(page.getByRole("tab").last()).toHaveAttribute(
    "href",
    "/settings/setup",
  )
  await page
    .getByRole("combobox", { name: "Storage Unit", exact: true })
    .click()
  await page.getByRole("option", { name: "TB", exact: true }).click()
  await page.getByLabel("Storage Capacity").fill("2")
  await page
    .getByRole("combobox", { name: "Operating System", exact: true })
    .click()
  await page.getByRole("option", { name: "Windows 11", exact: true }).click()
  await page.getByLabel("Mouse DPI", { exact: true }).fill("800")
  await page.getByLabel("Sensitivity", { exact: true }).fill("1.25")
  await expect(page.locator("#edpi")).toHaveText("1000")
  const saveButtons = page.getByRole("button", { name: "Save", exact: true })
  await expect(saveButtons).toHaveCount(2)
  await expect(
    page
      .locator("#settings-setup-actions")
      .getByRole("button", { name: "Save", exact: true }),
  ).toBeVisible()
  await saveButtons.first().click()
  await expect(page.getByText("Setup saved.")).toBeVisible()
  expect(saved.hardware[0].product_id).toBe(product.id)
  expect(saved.operating_system).toBe("Windows 11")
  expect(
    saved.hardware.find((item: any) => item.category === "storage")
      .storage_capacity_unit,
  ).toBe("TB")
  expect(
    saved.hardware.find((item: any) => item.category === "storage")
      .storage_capacity_gb,
  ).toBe(2000)
  const bottomSave = page.waitForRequest(
    (request) =>
      request.method() === "PUT" && request.url().endsWith("/v1/me/setup"),
  )
  await saveButtons.last().click()
  await bottomSave
  await expect(saveButtons.last()).toHaveClass(/self-end/)
  await page.reload()
  await expect(page.getByLabel("Mouse DPI", { exact: true })).toHaveValue("800")
  await expect(page.locator("#edpi")).toHaveText("1000")
  await expect(page.getByLabel("Storage Capacity")).toHaveValue("2")
  await expect(
    page.getByRole("combobox", { name: "Operating System", exact: true }),
  ).toHaveText("Windows 11")
  await page.screenshot({
    path: "../.temp/screenshots/gear-setup-desktop.png",
    fullPage: true,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(390)
  await page.screenshot({
    path: "../.temp/screenshots/gear-setup-mobile.png",
    fullPage: true,
  })
})

test("custom products can be added and selected immediately", async ({
  page,
}) => {
  await mock(page)
  await page.route("**/v1/products**", async (route) =>
    new URL(route.request().url()).pathname.endsWith("/brands")
      ? route.fulfill({ json: ["Logitech", "Razer"] })
      : route.request().method() === "POST"
        ? route.fulfill({
            json: {
              ...product,
              ...route.request().postDataJSON(),
              community_added: true,
            },
          })
        : route.fulfill({ json: { data: [], count: 0 } }),
  )
  await page.goto("/settings/setup")
  await page
    .getByRole("combobox", { name: "Mouse", exact: true })
    .fill("My Mouse")
  await page.getByRole("button", { name: "Add a custom model" }).click()
  await expect(page.getByLabel("Gear Type")).toHaveValue("Mouse")
  await page.getByRole("combobox", { name: "Brand", exact: true }).click()
  await page.getByRole("option", { name: "Logitech", exact: true }).click()
  await page.getByLabel("Product Link").fill("javascript:alert(1)")
  await expect(
    page.getByRole("button", { name: "Add and Select" }),
  ).toBeDisabled()
  await page.getByLabel("Product Link").fill("https://example.com/mouse")
  const submitted = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().endsWith("/v1/products"),
  )
  await page.screenshot({
    path: "../.temp/screenshots/gear-custom-desktop.png",
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: "../.temp/screenshots/gear-custom-mobile.png" })
  await page
    .getByRole("textbox", { name: "Model", exact: true })
    .fill("My Mouse")
  await page.getByRole("button", { name: "Add and Select" }).click()
  expect((await submitted).postDataJSON()).toMatchObject({
    category: "mouse",
    brand: "Logitech",
    product_url: "https://example.com/mouse",
  })
  await expect(
    page.getByRole("combobox", { name: "Mouse", exact: true }),
  ).toHaveValue("Logitech My Mouse")
})

test("gear product names open a safe web search by mouse or keyboard", async ({
  page,
  context,
}) => {
  await mock(page, false)
  await context.route("https://www.google.com/search?**", (route) =>
    route.fulfill({ body: "Search destination" }),
  )
  await page.goto("/leaderboards/gear")
  await expect(page.getByText("60.0%")).toBeVisible()
  const link = page.getByRole("link", {
    name: "Search for Logitech PRO X SUPERLIGHT 2 (opens in a new tab)",
  })
  await expect(link).toHaveAttribute(
    "href",
    "https://www.google.com/search?q=Logitech%20PRO%20X%20SUPERLIGHT%202",
  )
  await expect(link).toHaveAttribute("rel", "noopener noreferrer")
  await link.focus()
  const opened = context.waitForEvent("page")
  await page.keyboard.press("Enter")
  const search = await opened
  await search.waitForLoadState()
  expect(search.url()).toContain("https://www.google.com/search?q=")
  await search.close()
  await page.screenshot({
    path: "../.temp/screenshots/gear-rankings-desktop.png",
    fullPage: true,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: "../.temp/screenshots/gear-rankings-mobile.png",
    fullPage: true,
  })
})

test("gear pagination and category selection omit search and descriptions", async ({
  page,
}) => {
  await mock(page, false)
  const requests: URL[] = []
  await page.route("**/v1/leaderboards/gear**", async (route) => {
    const url = new URL(route.request().url())
    requests.push(url)
    return route.fulfill({
      json: {
        data: [{ rank: 1, product, players: 12, share: 12 }],
        count: 35,
        participants: 100,
      },
    })
  })
  await page.goto("/leaderboards/gear")
  await page
    .getByRole("button", { name: "Go to next page", exact: true })
    .click()
  await expect.poll(() => requests.at(-1)?.searchParams.get("skip")).toBe("20")
  await expect(page.getByPlaceholder("Search by brand or model…")).toHaveCount(
    0,
  )
  await expect(
    page.getByText("Self-reported setups.", { exact: false }),
  ).toHaveCount(0)
  await expect(
    page.getByText("players have shared a product", { exact: false }),
  ).toHaveCount(0)
  const categories = page.getByRole("group", { name: "Category", exact: true })
  await expect(categories.getByRole("button")).toHaveCount(13)
  await expect(
    categories.getByRole("button", { name: "Mouse", exact: true }),
  ).toHaveAttribute("aria-pressed", "true")
  await expect(page.getByText("Popular Gear", { exact: true })).toHaveCount(0)
  await expect(
    page.getByRole("combobox", { name: "Category", exact: true }),
  ).toHaveCount(0)
  await categories
    .getByRole("button", { name: "Keyboard", exact: true })
    .click()
  await expect(
    categories.getByRole("button", { name: "Keyboard", exact: true }),
  ).toHaveAttribute("aria-pressed", "true")
  await expect(
    categories.getByRole("button", { name: "Mouse", exact: true }),
  ).toHaveAttribute("aria-pressed", "false")
  await expect
    .poll(() => requests.at(-1)?.searchParams.get("category"))
    .toBe("keyboard")
  expect(requests.at(-1)?.searchParams.get("skip")).toBe("0")
  await expect(page.getByRole("tab").last()).toHaveAttribute(
    "href",
    "/leaderboards/gear",
  )
})

test("custom suggestions stay in the displayed category and allow missing brands", async ({
  page,
}) => {
  await mock(page)
  const queries: string[] = []
  await page.route("**/v1/products?**", async (route) => {
    queries.push(
      new URL(route.request().url()).searchParams.get("category") ?? "",
    )
    await route.fulfill({
      json: {
        data: [
          product,
          {
            ...product,
            id: "019d1111-1111-7111-8111-111111111112",
            category: "headset",
            model: "Wrong Headset",
          },
        ],
        count: 2,
      },
    })
  })
  await page.goto("/settings/setup")
  await page.getByRole("combobox", { name: "Mouse", exact: true }).fill("PRO")
  await page.getByRole("button", { name: "Add a custom model" }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog.getByLabel("Gear Type")).toHaveValue("Mouse")
  await expect(
    dialog.getByRole("button", { name: "Logitech PRO X SUPERLIGHT 2" }),
  ).toBeVisible()
  await expect(dialog.getByText("Logitech Wrong Headset")).toHaveCount(0)
  expect(queries.every((category) => category === "mouse")).toBe(true)
  await dialog.getByRole("combobox", { name: "Brand", exact: true }).click()
  await page.getByRole("option", { name: "Brand not listed" }).click()
  await dialog
    .getByRole("textbox", { name: "Other Brand", exact: true })
    .fill("New Brand")
  await expect(
    dialog.getByRole("button", { name: "Add and Select" }),
  ).toBeEnabled()
})

test("search panels dismiss automatically and setup labels stay concise", async ({
  page,
}) => {
  await mock(page)
  const brandCategories: string[] = []
  await page.route("**/v1/products/brands?**", (route) => {
    brandCategories.push(
      new URL(route.request().url()).searchParams.get("category") ?? "",
    )
    return route.fulfill({ json: ["Keychron"] })
  })
  await page.goto("/settings/setup")
  const mouse = page.getByRole("combobox", { name: "Mouse", exact: true })
  const keyboard = page.getByRole("combobox", { name: "Keyboard", exact: true })
  await mouse.click()
  await expect(mouse).toHaveAttribute("aria-expanded", "true")
  await keyboard.click()
  await expect(mouse).toHaveAttribute("aria-expanded", "false")
  await expect(keyboard).toHaveAttribute("aria-expanded", "true")
  await expect(
    page.getByRole("button", { name: "Add a custom model" }),
  ).toHaveCount(1)
  await page.getByText("Peripherals", { exact: true }).click()
  await expect(keyboard).toHaveAttribute("aria-expanded", "false")
  await keyboard.click()
  await page.keyboard.press("Escape")
  await expect(keyboard).toHaveAttribute("aria-expanded", "false")
  await keyboard.click()
  await page.getByRole("button", { name: "Add a custom model" }).click()
  const dialog = page.getByRole("dialog")
  await expect.poll(() => brandCategories).toEqual(["keyboard"])
  await dialog.getByRole("combobox", { name: "Brand", exact: true }).click()
  await expect(
    page.getByRole("option", { name: "Keychron", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("option", { name: "NVIDIA", exact: true }),
  ).toHaveCount(0)
  await page.keyboard.press("Escape")
  await expect(
    dialog.getByRole("textbox", { name: "Model", exact: true }),
  ).toHaveAttribute("aria-required", "true")
  await expect(dialog.getByLabel("Product Link", { exact: true })).toBeVisible()
  await expect(
    page.getByText("New models are immediately available to everyone.", {
      exact: false,
    }),
  ).toHaveCount(0)
  await expect(
    page.getByText("Add an HTTP or HTTPS product page", { exact: false }),
  ).toHaveCount(0)
  await expect(
    page.getByText("All fields are optional.", { exact: false }),
  ).toHaveCount(0)
  await expect(
    page.getByText("Enter the sensitivity value from CS:GO.", { exact: false }),
  ).toHaveCount(0)
  await expect(page.getByLabel("Memory Speed (MT/s)")).toHaveCount(0)
  await page.screenshot({
    path: "../.temp/screenshots/gear-custom-desktop.png",
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: "../.temp/screenshots/gear-custom-mobile.png" })
})

test("brands are searchable and gear configuration stays beside its selection", async ({
  page,
}) => {
  await mock(page)
  await page.goto("/settings/setup")
  const mouse = page.getByRole("combobox", { name: "Mouse", exact: true })
  await mouse.fill("Superlight")
  await page
    .getByRole("option", { name: "Logitech PRO X SUPERLIGHT 2" })
    .click()
  await expect(mouse).toHaveValue("Logitech PRO X SUPERLIGHT 2")
  await expect(
    page
      .locator('[data-gear="mouse"]')
      .getByLabel("Mouse DPI", { exact: true }),
  ).toBeVisible()
  await expect(
    page.locator('[data-gear="monitor"]').locator("#monitor-refresh"),
  ).toBeVisible()
  await expect(
    page.locator('[data-gear="memory"]').locator("#memory-capacity"),
  ).toBeVisible()
  await expect(
    page.locator('[data-gear="memory"]').locator("#memory-type"),
  ).toBeVisible()
  await page.getByRole("button", { name: "Clear Mouse", exact: true }).click()
  await expect(mouse).toHaveValue("")
  await mouse.click()
  await page.getByRole("button", { name: "Add a custom model" }).click()
  await page.getByRole("combobox", { name: "Brand", exact: true }).click()
  await expect(page.getByRole("option").first()).toHaveText("Brand not listed")
  await page.getByRole("combobox", { name: "Search brands…" }).fill("raZ")
  await expect(
    page.getByRole("option", { name: "Logitech", exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole("option", { name: "Razer", exact: true }),
  ).toBeVisible()
  await page.keyboard.press("ArrowDown")
  await page.keyboard.press("Enter")
  await expect(
    page.getByRole("combobox", { name: "Brand", exact: true }),
  ).toHaveText("Razer")
})
