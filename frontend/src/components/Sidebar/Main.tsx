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
}

function isPathActive(path: string, currentPath: string) {
  return path === "/"
    ? currentPath === "/"
    : currentPath === path || currentPath.startsWith(`${path}/`)
}

function MainMenuLink({
  item,
  currentPath,
  onNavigate,
}: {
  item: LinkItem
  currentPath: string
  onNavigate: () => void
}) {
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        tooltip={item.title}
        isActive={isPathActive(item.path, currentPath)}
        asChild
      >
        <RouterLink to={item.path} onClick={onNavigate}>
          <item.icon />
          <span>{item.title}</span>
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

export function Main({ items }: MainProps) {
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
