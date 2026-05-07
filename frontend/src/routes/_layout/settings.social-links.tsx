import { createFileRoute } from "@tanstack/react-router"

import SocialLinksSettings from "@/components/UserSettings/SocialLinksSettings"

export const Route = createFileRoute("/_layout/settings/social-links")({
  component: SettingsSocialLinksRoute,
})

function SettingsSocialLinksRoute() {
  return <SocialLinksSettings />
}
