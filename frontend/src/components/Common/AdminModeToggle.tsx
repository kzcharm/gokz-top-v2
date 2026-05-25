import { Shield } from "lucide-react"

import { useAdminMode } from "@/components/admin-mode-provider"
import { Button } from "@/components/ui/button"
import useAuth from "@/hooks/useAuth"
import { canModerateBansAndRecords } from "@/lib/user-roles"
import { cn } from "@/lib/utils"

export function AdminModeToggle() {
  const { enabled, toggle } = useAdminMode()
  const { user } = useAuth()

  if (!canModerateBansAndRecords(user)) {
    return null
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={cn(
        "rounded-full",
        enabled &&
          "bg-destructive/10 text-destructive hover:bg-destructive/15 hover:text-destructive",
      )}
      aria-pressed={enabled}
      aria-label="Admin mode"
      title="Admin mode"
      onClick={toggle}
    >
      <Shield className="size-4" />
    </Button>
  )
}
