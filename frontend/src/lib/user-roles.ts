import type { UserPublic, UserRole } from "@/client"

export const USER_ROLE_LABELS: Record<UserRole, string> = {
  superuser: "Superuser",
  admin: "Admin",
  map_admin: "Map Admin",
  server_owner: "Server Owner",
}

export const USER_ROLE_OPTIONS: Array<{
  description: string
  label: string
  value: UserRole
}> = [
  {
    value: "superuser",
    label: "Superuser",
    description: "Full access to all admin pages and user role management.",
  },
  {
    value: "admin",
    label: "Admin",
    description:
      "Can add bans and moderate record validity without root access.",
  },
  {
    value: "map_admin",
    label: "Map Admin",
    description:
      "Full access to the admin maps page and map record-filter tiers.",
  },
  {
    value: "server_owner",
    label: "Server Owner",
    description:
      "Access the admin servers page and manage server resources you own.",
  },
]

export const USER_ROLE_ORDER: UserRole[] = [
  "superuser",
  "admin",
  "map_admin",
  "server_owner",
]

export const USER_ROLE_BADGE_CLASS_NAMES: Record<UserRole, string> = {
  superuser: "border-transparent bg-[#009486] text-white",
  admin: "border-transparent bg-[#b91c1c] text-white",
  map_admin: "border-transparent bg-[#1d4ed8] text-white",
  server_owner: "border-transparent bg-[#f59e0b] text-white",
}

export type PlayerPermissionLevel = UserRole | "user"

export const PLAYER_PERMISSION_RING_CLASS_NAMES: Record<
  PlayerPermissionLevel,
  string
> = {
  superuser: "ring-[#009486]/90",
  admin: "ring-[#ef4444]/90",
  map_admin: "ring-[#1d4ed8]/90",
  server_owner: "ring-[#f59e0b]/90",
  user: "ring-pink-400/90",
}

export function hasRole(
  user: Pick<UserPublic, "roles"> | null | undefined,
  role: UserRole,
) {
  return Boolean(user?.roles?.includes(role))
}

export function getHighestPlayerPermission(
  roles: UserRole[] | null | undefined,
): PlayerPermissionLevel | null {
  if (roles === undefined) {
    return null
  }
  if (roles === null) {
    return null
  }
  if (roles.length === 0) {
    return "user"
  }

  for (const role of USER_ROLE_ORDER) {
    if (roles.includes(role)) {
      return role
    }
  }

  return "user"
}

export function isSuperuser(
  user: Pick<UserPublic, "roles"> | null | undefined,
) {
  return hasRole(user, "superuser")
}

export function canModerateBansAndRecords(
  user: Pick<UserPublic, "roles"> | null | undefined,
) {
  return hasRole(user, "superuser") || hasRole(user, "admin")
}

export function canAccessAdminMaps(
  user: Pick<UserPublic, "roles"> | null | undefined,
) {
  return hasRole(user, "superuser") || hasRole(user, "map_admin")
}
