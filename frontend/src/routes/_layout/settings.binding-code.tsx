import { createFileRoute } from "@tanstack/react-router"

import QqBindingCodeSettings from "@/components/UserSettings/QqBindingCodeSettings"

export const Route = createFileRoute("/_layout/settings/binding-code")({
  component: SettingsBindingCodeRoute,
})

function SettingsBindingCodeRoute() {
  return <QqBindingCodeSettings />
}
