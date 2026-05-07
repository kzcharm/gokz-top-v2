import { Link as RouterLink, useRouterState } from "@tanstack/react-router"
import { ChevronRight, type LucideIcon } from "lucide-react"
import { useEffect, useState } from "react"

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { cn } from "@/lib/utils"

type LinkItem = {
  type: "link"
  icon: LucideIcon
  title: string
  path: string
  activePrefixes?: string[]
  showNotificationDot?: boolean
}

type GroupChildItem = {
  title: string
  path: string
  icon?: LucideIcon
}

type GroupItem = {
  type: "group"
  icon: LucideIcon
  title: string
  pathPrefix: string
  children: GroupChildItem[]
}

export type Item = LinkItem | GroupItem

interface MainProps {
  items: Item[]
  onLinkNavigate?: (path: string) => void
}

function isPathActive(path: string, currentPath: string) {
  return path === "/"
    ? currentPath === "/"
    : currentPath === path || currentPath.startsWith(`${path}/`)
}

function isLinkItemActive(item: LinkItem, currentPath: string) {
  if (isPathActive(item.path, currentPath)) {
    return true
  }

  if (!item.activePrefixes) {
    return false
  }

  return item.activePrefixes.some((prefix) => isPathActive(prefix, currentPath))
}

function MainMenuLink({
  item,
  currentPath,
  onNavigate,
  onLinkNavigate,
}: {
  item: LinkItem
  currentPath: string
  onNavigate: () => void
  onLinkNavigate?: (path: string) => void
}) {
  const isActive = isLinkItemActive(item, currentPath)

  return (
    <SidebarMenuItem>
      <SidebarMenuButton tooltip={item.title} isActive={isActive} asChild>
        <RouterLink
          to={item.path}
          onClick={() => {
            onLinkNavigate?.(item.path)
            onNavigate()
          }}
        >
          <item.icon />
          <span className="flex items-center gap-2">
            <span>{item.title}</span>
            {item.showNotificationDot && !isActive ? (
              <span
                aria-hidden="true"
                className="size-2 shrink-0 rounded-full bg-red-500 animate-pulse"
              />
            ) : null}
          </span>
        </RouterLink>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

function MainMenuGroup({
  item,
  currentPath,
  onNavigate,
}: {
  item: GroupItem
  currentPath: string
  onNavigate: () => void
}) {
  const isRouteActive = isPathActive(item.pathPrefix, currentPath)
  const [isOpen, setIsOpen] = useState(isRouteActive)

  useEffect(() => {
    if (isRouteActive) {
      setIsOpen(true)
    }
  }, [isRouteActive])

  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        tooltip={item.title}
        isActive={isRouteActive}
        onClick={() => setIsOpen((open) => !open)}
        className="cursor-pointer"
        aria-expanded={isOpen}
      >
        <item.icon />
        <span>{item.title}</span>
        <ChevronRight
          className={cn(
            "ml-auto size-4 transition-transform group-data-[collapsible=icon]:hidden",
            isOpen && "rotate-90",
          )}
        />
      </SidebarMenuButton>
      {isOpen ? (
        <SidebarMenuSub>
          {item.children.map((child) => (
            <SidebarMenuSubItem key={child.path}>
              <SidebarMenuSubButton
                asChild
                isActive={isPathActive(child.path, currentPath)}
              >
                <RouterLink to={child.path} onClick={onNavigate}>
                  {child.icon ? <child.icon /> : null}
                  <span>{child.title}</span>
                </RouterLink>
              </SidebarMenuSubButton>
            </SidebarMenuSubItem>
          ))}
        </SidebarMenuSub>
      ) : null}
    </SidebarMenuItem>
  )
}

export function Main({ items, onLinkNavigate }: MainProps) {
  const { isMobile, setOpenMobile } = useSidebar()
  const router = useRouterState()
  const currentPath = router.location.pathname

  const handleMenuClick = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }

  return (
    <SidebarGroup>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => {
            return item.type === "link" ? (
              <MainMenuLink
                key={item.path}
                item={item}
                currentPath={currentPath}
                onNavigate={handleMenuClick}
                onLinkNavigate={onLinkNavigate}
              />
            ) : (
              <MainMenuGroup
                key={item.pathPrefix}
                item={item}
                currentPath={currentPath}
                onNavigate={handleMenuClick}
              />
            )
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
