import { createFileRoute } from "@tanstack/react-router"

import AppearanceSettings from "@/components/UserSettings/AppearanceSettings"

export const Route = createFileRoute("/_layout/settings/appearance")({
  component: SettingsAppearanceRoute,
})

function SettingsAppearanceRoute() {
  return <AppearanceSettings />
}
