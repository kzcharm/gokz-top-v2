import type { UserRole } from "@/client"
import { Badge } from "@/components/ui/badge"
import { USER_ROLE_LABELS } from "@/lib/user-roles"

const USER_ROLE_BADGE_CLASS_NAMES: Record<UserRole, string> = {
  superuser: "border-transparent bg-[#009486] text-white",
  admin: "border-transparent bg-[#b91c1c] text-white",
  map_admin: "border-transparent bg-[#1d4ed8] text-white",
  server_owner: "border-transparent bg-[#f59e0b] text-white",
}

export function UserRoleBadge({ role }: { role: UserRole }) {
  return (
    <Badge className={USER_ROLE_BADGE_CLASS_NAMES[role]}>
      {USER_ROLE_LABELS[role]}
    </Badge>
  )
}
