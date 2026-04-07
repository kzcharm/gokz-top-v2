import { Link as RouterLink, useRouterState } from "@tanstack/react-router"
import { ChevronRight } from "lucide-react"
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
import {
  moveSidebarEntry,
  type ResolvedSidebarEntry,
  type ResolvedSidebarGroupEntry,
  type ResolvedSidebarLinkEntry,
  type SidebarDropContainer,
  type SidebarItemId,
  type SidebarLayout,
  type SidebarTopLevelEntryId,
} from "./sidebar-layout"

interface MainProps {
  items: ResolvedSidebarEntry[]
  layout: SidebarLayout
  onLayoutChange: (layout: SidebarLayout) => void
}

function isPathActive(path: string, currentPath: string) {
  return path === "/"
    ? currentPath === "/"
    : currentPath === path || currentPath.startsWith(`${path}/`)
}

function isLinkItemActive(item: ResolvedSidebarLinkEntry, currentPath: string) {
  if (isPathActive(item.path, currentPath)) {
    return true
  }

  if (!item.activePrefixes) {
    return false
  }

  return item.activePrefixes.some((prefix) => isPathActive(prefix, currentPath))
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

function encodeDragPayload(payload: DragPayload) {
  return JSON.stringify(payload)
}

function parseDragPayload(rawValue: string): DragPayload | null {
  try {
    const parsed = JSON.parse(rawValue) as DragPayload
    if (
      parsed &&
      typeof parsed === "object" &&
      ((parsed.kind === "group" &&
        parsed.id === "others" &&
        parsed.container === "root") ||
        (parsed.kind === "item" &&
          typeof parsed.id === "string" &&
          (parsed.container === "root" || parsed.container === "others")))
    ) {
      return parsed
    }
  } catch {
    return null
  }

  return null
}

function useDropHandler(
  layout: SidebarLayout,
  onLayoutChange: (layout: SidebarLayout) => void,
) {
  return (
    event: React.DragEvent<HTMLElement>,
    destination: {
      container: SidebarDropContainer
      targetId: SidebarTopLevelEntryId | SidebarItemId | null
    },
  ) => {
    event.preventDefault()
    event.stopPropagation()

    const payload = parseDragPayload(
      event.dataTransfer.getData("application/gokz-sidebar-item"),
    )
    if (!payload) {
      return
    }

    const nextLayout = moveSidebarEntry(layout, payload, destination)
    onLayoutChange(nextLayout)
  }
}

function MainMenuLink({
  item,
  currentPath,
  onNavigate,
  onDropItem,
  onDragStart,
}: {
  item: ResolvedSidebarLinkEntry
  currentPath: string
  onNavigate: () => void
  onDropItem: (event: React.DragEvent<HTMLElement>) => void
  onDragStart?: (event: React.DragEvent<HTMLElement>) => void
}) {
  return (
    <SidebarMenuItem
      data-testid={`sidebar-item-${item.id}`}
      onDragOver={item.draggable ? (event) => event.preventDefault() : undefined}
      onDrop={item.draggable ? onDropItem : undefined}
    >
      <SidebarMenuButton
        tooltip={item.title}
        isActive={isLinkItemActive(item, currentPath)}
        asChild
        draggable={item.draggable}
        onDragStart={onDragStart}
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
  onOtherDrop,
  onDragStart,
}: {
  item: ResolvedSidebarGroupEntry
  currentPath: string
  onNavigate: () => void
  onOtherDrop: (
    event: React.DragEvent<HTMLElement>,
    targetId: SidebarItemId | null,
  ) => void
  onDragStart?: (event: React.DragEvent<HTMLElement>) => void
}) {
  const isRouteActive =
    item.id === "others"
      ? item.children.some((child) => isLinkItemActive(child, currentPath))
      : isPathActive(item.pathPrefix, currentPath)
  const [isOpen, setIsOpen] = useState(isRouteActive)

  useEffect(() => {
    if (isRouteActive) {
      setIsOpen(true)
    }
  }, [isRouteActive])

  return (
    <SidebarMenuItem data-testid={`sidebar-group-${item.id}`}>
      <SidebarMenuButton
        tooltip={item.title}
        isActive={isRouteActive}
        onClick={() => setIsOpen((open) => !open)}
        className="cursor-pointer"
        aria-expanded={isOpen}
        draggable={item.draggable}
        onDragStart={onDragStart}
        onDragOver={item.id === "others" ? (event) => event.preventDefault() : undefined}
        onDrop={item.id === "others" ? (event) => onOtherDrop(event, null) : undefined}
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
        <SidebarMenuSub
          data-testid={`sidebar-group-${item.id}-content`}
          onDragOver={
            item.id === "others" ? (event) => event.preventDefault() : undefined
          }
          onDrop={
            item.id === "others"
              ? (event) => onOtherDrop(event, null)
              : undefined
          }
        >
          {item.children.map((child) => (
            <SidebarMenuSubItem
              key={child.path}
              data-testid={`sidebar-item-${child.id}`}
              onDragOver={
                item.id === "others" ? (event) => event.preventDefault() : undefined
              }
              onDrop={
                item.id === "others"
                  ? (event) => onOtherDrop(event, child.id as SidebarItemId)
                  : undefined
              }
            >
              <SidebarMenuSubButton
                asChild
                isActive={isPathActive(child.path, currentPath)}
                draggable={item.id === "others"}
                onDragStart={
                  item.id === "others"
                    ? (event) => {
                        event.dataTransfer.effectAllowed = "move"
                        event.dataTransfer.setData(
                          "application/gokz-sidebar-item",
                          encodeDragPayload({
                            kind: "item",
                            id: child.id as SidebarItemId,
                            container: "others",
                          }),
                        )
                      }
                    : undefined
                }
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

export function Main({ items, layout, onLayoutChange }: MainProps) {
  const { isMobile, setOpenMobile } = useSidebar()
  const router = useRouterState()
  const currentPath = router.location.pathname
  const handleDrop = useDropHandler(layout, onLayoutChange)

  const handleMenuClick = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }

  const handleRootDragStart = (
    event: React.DragEvent<HTMLElement>,
    itemId: SidebarTopLevelEntryId,
  ) => {
    const payload: DragPayload =
      itemId === "others"
        ? { kind: "group", id: "others", container: "root" }
        : { kind: "item", id: itemId, container: "root" }
    event.dataTransfer.effectAllowed = "move"
    event.dataTransfer.setData(
      "application/gokz-sidebar-item",
      encodeDragPayload(payload),
    )
  }

  return (
    <SidebarGroup>
      <SidebarGroupContent>
        <SidebarMenu
          data-testid="sidebar-root"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) =>
            handleDrop(event, { container: "root", targetId: null })
          }
        >
          {items.map((item) => {
            return item.type === "link" ? (
              <MainMenuLink
                key={item.path}
                item={item}
                currentPath={currentPath}
                onNavigate={handleMenuClick}
                onDropItem={(event) =>
                  handleDrop(event, { container: "root", targetId: item.id })
                }
                onDragStart={(event) => handleRootDragStart(event, item.id)}
              />
            ) : (
              <MainMenuGroup
                key={item.id}
                item={item}
                currentPath={currentPath}
                onNavigate={handleMenuClick}
                onOtherDrop={(event, targetId) =>
                  handleDrop(event, {
                    container: "others",
                    targetId,
                  })
                }
                onDragStart={
                  item.id === "others"
                    ? (event) => handleRootDragStart(event, "others")
                    : undefined
                }
              />
            )
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
