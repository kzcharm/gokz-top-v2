import {
  Activity,
  Folder,
  Home,
  Map,
  Server,
  Settings,
  ShieldAlert,
  Trophy,
  User as UserIcon,
  UserCircle2,
  Users,
  type LucideIcon,
} from "lucide-react"

export const FALLBACK_PROFILE_STEAMID64 = "76561198417871586"
export const SIDEBAR_LAYOUT_STORAGE_KEY = "gokz-sidebar-layout-v1"

export const SIDEBAR_ITEM_IDS = [
  "servers",
  "profile",
  "leaderboards",
  "dashboard",
  "maps",
  "live",
  "bans",
  "settings",
] as const

export type SidebarItemId = (typeof SIDEBAR_ITEM_IDS)[number]
export type SidebarTopLevelEntryId = SidebarItemId | "others"
export type SidebarDropContainer = "root" | "others"

export interface SidebarLayout {
  topLevel: SidebarTopLevelEntryId[]
  others: SidebarItemId[]
}

type BaseSidebarEntry = {
  title: string
  icon: LucideIcon
  draggable?: boolean
}

export type ResolvedSidebarLinkEntry<TId extends string = string> =
  BaseSidebarEntry & {
  type: "link"
  id: TId
  path: string
  activePrefixes?: string[]
}

export type ResolvedSidebarGroupEntry = BaseSidebarEntry & {
  type: "group"
  id: "others" | "admin"
  pathPrefix: string
  children: ResolvedSidebarLinkEntry[]
}

export type ResolvedSidebarEntry =
  | ResolvedSidebarLinkEntry<SidebarItemId>
  | ResolvedSidebarGroupEntry

type SidebarItemDefinition = Omit<ResolvedSidebarLinkEntry<SidebarItemId>, "path"> & {
  path: (profileSteamid64: string) => string
}

const SIDEBAR_ITEM_SET = new Set<string>(SIDEBAR_ITEM_IDS)

const SIDEBAR_ITEM_DEFINITIONS: Record<SidebarItemId, SidebarItemDefinition> = {
  servers: {
    type: "link",
    id: "servers",
    icon: Server,
    title: "Servers",
    path: () => "/servers",
  },
  profile: {
    type: "link",
    id: "profile",
    icon: UserCircle2,
    title: "Profile",
    path: (profileSteamid64) => `/profile/${profileSteamid64}`,
    activePrefixes: ["/profile"],
  },
  leaderboards: {
    type: "link",
    id: "leaderboards",
    icon: Trophy,
    title: "Leaderboards",
    path: () => "/leaderboards",
  },
  dashboard: {
    type: "link",
    id: "dashboard",
    icon: Home,
    title: "Dashboard",
    path: () => "/dashboard",
  },
  maps: {
    type: "link",
    id: "maps",
    icon: Map,
    title: "Maps",
    path: () => "/maps",
  },
  live: {
    type: "link",
    id: "live",
    icon: Activity,
    title: "Live",
    path: () => "/live",
  },
  bans: {
    type: "link",
    id: "bans",
    icon: ShieldAlert,
    title: "Bans",
    path: () => "/bans",
  },
  settings: {
    type: "link",
    id: "settings",
    icon: Settings,
    title: "Settings",
    path: () => "/settings",
  },
}

const ADMIN_GROUP: ResolvedSidebarGroupEntry = {
  type: "group",
  id: "admin",
  icon: Users,
  title: "Admin",
  pathPrefix: "/admin",
  children: [
    {
      type: "link",
      id: "admin-users",
      title: "Users",
      path: "/admin/users",
      icon: Users,
    },
    {
      type: "link",
      id: "admin-players",
      title: "Players",
      path: "/admin/players",
      icon: UserIcon,
    },
  ],
}

export const DEFAULT_SIDEBAR_LAYOUT: SidebarLayout = {
  topLevel: [
    "servers",
    "profile",
    "leaderboards",
    "dashboard",
    "maps",
    "live",
    "settings",
    "others",
  ],
  others: ["bans"],
}

function isSidebarItemId(value: unknown): value is SidebarItemId {
  return typeof value === "string" && SIDEBAR_ITEM_SET.has(value)
}

function isSidebarTopLevelEntryId(value: unknown): value is SidebarTopLevelEntryId {
  return value === "others" || isSidebarItemId(value)
}

export function sanitizeSidebarLayout(candidate: unknown): SidebarLayout {
  if (!candidate || typeof candidate !== "object") {
    return DEFAULT_SIDEBAR_LAYOUT
  }

  const { others, topLevel } = candidate as Partial<SidebarLayout>
  const normalizedOthers: SidebarItemId[] = []

  if (Array.isArray(others)) {
    for (const entry of others) {
      if (isSidebarItemId(entry) && !normalizedOthers.includes(entry)) {
        normalizedOthers.push(entry)
      }
    }
  }

  const othersSet = new Set(normalizedOthers)
  const normalizedTopLevel: SidebarTopLevelEntryId[] = []
  const topLevelItems = new Set<SidebarItemId>()

  if (Array.isArray(topLevel)) {
    for (const entry of topLevel) {
      if (!isSidebarTopLevelEntryId(entry)) {
        continue
      }
      if (entry === "others") {
        if (!normalizedTopLevel.includes("others")) {
          normalizedTopLevel.push("others")
        }
        continue
      }
      if (othersSet.has(entry) || topLevelItems.has(entry)) {
        continue
      }
      normalizedTopLevel.push(entry)
      topLevelItems.add(entry)
    }
  }

  for (const itemId of SIDEBAR_ITEM_IDS) {
    if (!othersSet.has(itemId) && !topLevelItems.has(itemId)) {
      normalizedTopLevel.push(itemId)
    }
  }

  if (!normalizedTopLevel.includes("others")) {
    normalizedTopLevel.push("others")
  }

  return {
    topLevel: normalizedTopLevel,
    others: normalizedOthers,
  }
}

export function getStoredSidebarLayout(): SidebarLayout {
  if (typeof window === "undefined") {
    return DEFAULT_SIDEBAR_LAYOUT
  }

  const rawValue = window.localStorage.getItem(SIDEBAR_LAYOUT_STORAGE_KEY)
  if (!rawValue) {
    return DEFAULT_SIDEBAR_LAYOUT
  }

  try {
    return sanitizeSidebarLayout(JSON.parse(rawValue))
  } catch {
    return DEFAULT_SIDEBAR_LAYOUT
  }
}

export function saveSidebarLayout(layout: SidebarLayout) {
  if (typeof window === "undefined") {
    return
  }

  window.localStorage.setItem(
    SIDEBAR_LAYOUT_STORAGE_KEY,
    JSON.stringify(sanitizeSidebarLayout(layout)),
  )
}

function resolveSidebarLink(
  itemId: SidebarItemId,
  profileSteamid64: string,
): ResolvedSidebarLinkEntry<SidebarItemId> {
  const definition = SIDEBAR_ITEM_DEFINITIONS[itemId]
  return {
    ...definition,
    path: definition.path(profileSteamid64),
  }
}

export function resolveSidebarItems(params: {
  currentUserIsSuperuser: boolean
  profileSteamid64?: string | null
  layout?: SidebarLayout
}): ResolvedSidebarEntry[] {
  const profileSteamid64 =
    params.profileSteamid64 ?? FALLBACK_PROFILE_STEAMID64
  const layout = sanitizeSidebarLayout(params.layout ?? DEFAULT_SIDEBAR_LAYOUT)
  const othersChildren = layout.others.map((itemId) =>
    resolveSidebarLink(itemId, profileSteamid64),
  )

  const resolvedEntries: ResolvedSidebarEntry[] = []

  for (const entryId of layout.topLevel) {
    if (entryId === "others") {
      if (othersChildren.length > 0) {
        resolvedEntries.push({
          type: "group",
          id: "others",
          icon: Folder,
          title: "Others",
          pathPrefix: "",
          children: othersChildren,
          draggable: true,
        })
      }
      continue
    }

    resolvedEntries.push({
      ...resolveSidebarLink(entryId, profileSteamid64),
      draggable: true,
    })
  }

  if (params.currentUserIsSuperuser) {
    resolvedEntries.push(ADMIN_GROUP)
  }

  return resolvedEntries
}

export function getFirstSidebarLeafPath(params: {
  layout?: SidebarLayout
  profileSteamid64?: string | null
}): string {
  const profileSteamid64 =
    params.profileSteamid64 ?? FALLBACK_PROFILE_STEAMID64
  const layout = sanitizeSidebarLayout(params.layout ?? DEFAULT_SIDEBAR_LAYOUT)

  for (const entryId of layout.topLevel) {
    if (entryId === "others") {
      if (layout.others.length > 0) {
        return resolveSidebarLink(layout.others[0], profileSteamid64).path
      }
      continue
    }
    return resolveSidebarLink(entryId, profileSteamid64).path
  }

  return resolveSidebarLink("profile", profileSteamid64).path
}

type DragPayload =
  | {
      kind: "group"
      id: "others"
      container: "root"
    }
  | {
      kind: "item"
      id: SidebarItemId
      container: SidebarDropContainer
    }

function removeRootEntry(
  topLevel: SidebarTopLevelEntryId[],
  entryId: SidebarTopLevelEntryId,
) {
  return topLevel.filter((entry) => entry !== entryId)
}

function insertBefore<T>(items: T[], nextItem: T | null, value: T) {
  if (nextItem === null) {
    return [...items, value]
  }

  const targetIndex = items.indexOf(nextItem)
  if (targetIndex === -1) {
    return [...items, value]
  }

  return [
    ...items.slice(0, targetIndex),
    value,
    ...items.slice(targetIndex),
  ]
}

export function moveSidebarEntry(
  layout: SidebarLayout,
  payload: DragPayload,
  destination: {
    container: SidebarDropContainer
    targetId: SidebarTopLevelEntryId | SidebarItemId | null
  },
): SidebarLayout {
  const currentLayout = sanitizeSidebarLayout(layout)

  if (payload.kind === "group") {
    if (destination.container !== "root") {
      return currentLayout
    }
    if (destination.targetId === "others") {
      return currentLayout
    }

    return {
      ...currentLayout,
      topLevel: insertBefore(
        removeRootEntry(currentLayout.topLevel, "others"),
        destination.targetId as SidebarTopLevelEntryId | null,
        "others",
      ),
    }
  }

  if (destination.container === payload.container && destination.targetId === payload.id) {
    return currentLayout
  }

  const nextTopLevel =
    payload.container === "root"
      ? removeRootEntry(currentLayout.topLevel, payload.id)
      : currentLayout.topLevel
  const nextOthers =
    payload.container === "others"
      ? currentLayout.others.filter((entry) => entry !== payload.id)
      : currentLayout.others

  if (destination.container === "root") {
    if (destination.targetId === payload.id) {
      return currentLayout
    }

    return sanitizeSidebarLayout({
      topLevel: insertBefore(
        nextTopLevel,
        destination.targetId as SidebarTopLevelEntryId | null,
        payload.id,
      ),
      others: nextOthers,
    })
  }

  if (destination.targetId === "others") {
    return currentLayout
  }

  return sanitizeSidebarLayout({
    topLevel: nextTopLevel,
    others: insertBefore(
      nextOthers,
      destination.targetId as SidebarItemId | null,
      payload.id,
    ),
  })
}
