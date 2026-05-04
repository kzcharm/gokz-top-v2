import type { UserPublic, UserRole } from "@/client"

export const USER_ROLE_LABELS: Record<UserRole, string> = {
  superuser: "Superuser",
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

export function hasRole(
  user: Pick<UserPublic, "roles"> | null | undefined,
  role: UserRole,
) {
  return Boolean(user?.roles?.includes(role))
}

export function isSuperuser(
  user: Pick<UserPublic, "roles"> | null | undefined,
) {
  return hasRole(user, "superuser")
}

export function canAccessAdminMaps(
  user: Pick<UserPublic, "roles"> | null | undefined,
) {
  return hasRole(user, "superuser") || hasRole(user, "map_admin")
}
