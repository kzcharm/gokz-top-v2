import { createFileRoute } from "@tanstack/react-router"

import WebhooksSettings from "@/components/UserSettings/WebhooksSettings"

export const Route = createFileRoute("/_layout/settings/webhooks")({
  component: SettingsWebhooksRoute,
})

function SettingsWebhooksRoute() {
  return <WebhooksSettings />
}
