import type { UserRole } from "@/client"
import { Badge } from "@/components/ui/badge"
import { USER_ROLE_BADGE_CLASS_NAMES, USER_ROLE_LABELS } from "@/lib/user-roles"

export function UserRoleBadge({ role }: { role: UserRole }) {
  return (
    <Badge className={USER_ROLE_BADGE_CLASS_NAMES[role]}>
      {USER_ROLE_LABELS[role]}
    </Badge>
  )
}
