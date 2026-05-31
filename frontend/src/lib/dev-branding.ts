import { IS_LOCAL_DEV } from "@/lib/site"

const DEV_APPLE_TOUCH_ICON_HREF = "/apple-touch-icon-dev.png"
const DEV_FAVICON_32_HREF = "/favicon-dev-32x32.png"
const DEV_FAVICON_16_HREF = "/favicon-dev-16x16.png"
const DEV_FAVICON_ICO_HREF = "/favicon-dev.ico"

export function applyDevBranding() {
  if (!IS_LOCAL_DEV) {
    return
  }

  for (const link of document.querySelectorAll<HTMLLinkElement>(
    'link[rel~="icon"], link[rel="apple-touch-icon"]',
  )) {
    link.remove()
  }

  const appleTouchIcon = document.createElement("link")
  appleTouchIcon.rel = "apple-touch-icon"
  appleTouchIcon.sizes = "180x180"
  appleTouchIcon.href = DEV_APPLE_TOUCH_ICON_HREF

  const favicon32 = document.createElement("link")
  favicon32.rel = "icon"
  favicon32.type = "image/png"
  favicon32.sizes = "32x32"
  favicon32.href = DEV_FAVICON_32_HREF

  const favicon16 = document.createElement("link")
  favicon16.rel = "icon"
  favicon16.type = "image/png"
  favicon16.sizes = "16x16"
  favicon16.href = DEV_FAVICON_16_HREF

  const faviconIco = document.createElement("link")
  faviconIco.rel = "icon"
  faviconIco.type = "image/x-icon"
  faviconIco.href = DEV_FAVICON_ICO_HREF

  document.head.append(appleTouchIcon, favicon32, favicon16, faviconIco)
}
