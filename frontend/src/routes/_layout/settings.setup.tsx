import { createFileRoute } from "@tanstack/react-router"
import { SetupEditor } from "@/components/Gear/SetupEditor"
export const Route = createFileRoute("/_layout/settings/setup")({
  component: SetupEditor,
})
