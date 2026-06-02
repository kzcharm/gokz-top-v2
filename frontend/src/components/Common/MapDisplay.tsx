import { Link, useNavigate } from "@tanstack/react-router"
import { Copy, MapIcon } from "lucide-react"
import type { KeyboardEvent, MouseEvent, ReactNode } from "react"
import { useState } from "react"
import { toast } from "sonner"

import { OpenAPI } from "@/client/core/OpenAPI"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import { cn } from "@/lib/utils"

interface MapDisplayProps {
  mapName: string | null | undefined
  className?: string
  contextMenuItems?: ReactNode
  imageUrls?: string[]
}

export function getMapImageUrl(mapName: string | null | undefined) {
  if (!mapName || mapName.trim() === "") {
    return null
  }

  return `https://github.com/KZGlobalTeam/map-images/raw/public/webp/${mapName}.webp`
}

function buildApiUrl(path: string) {
  const configuredBase = OpenAPI.BASE || window.location.origin
  const baseUrl = new URL(configuredBase, window.location.origin)
  const normalizedBasePath =
    baseUrl.pathname === "/" ? "" : baseUrl.pathname.replace(/\/$/, "")

  return `${baseUrl.origin}${normalizedBasePath}${path}`
}

export function getWorkshopPreviewImageUrl(
  workshopId: number | string | null | undefined,
) {
  const normalizedWorkshopId = String(workshopId ?? "").trim()
  if (!normalizedWorkshopId || !/^\d+$/.test(normalizedWorkshopId)) {
    return null
  }

  return buildApiUrl(
    `/v1/maps/workshop/${encodeURIComponent(normalizedWorkshopId)}/preview-image`,
  )
}

export function getMapImageUrls(
  mapName: string | null | undefined,
  workshopId?: number | string | null,
) {
  return [
    getMapImageUrl(mapName),
    getWorkshopPreviewImageUrl(workshopId),
  ].filter((url): url is string => Boolean(url))
}

export function MapDisplay({
  mapName,
  className,
  contextMenuItems,
  imageUrls,
}: MapDisplayProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [, copyToClipboard] = useCopyToClipboard()
  const navigate = useNavigate()

  if (!mapName || mapName.trim() === "") {
    return <span className="text-muted-foreground">-</span>
  }

  const resolvedImageUrls =
    imageUrls && imageUrls.length > 0 ? imageUrls : getMapImageUrls(mapName)
  const mapParams = { mapName }

  const handleGoToMapPage = () => {
    void navigate({ to: "/maps/$mapName/maptop", params: mapParams })
  }

  const handleCopyMapName = async () => {
    const didCopy = await copyToClipboard(mapName)

    if (didCopy) {
      toast.success("Map name copied", {
        description: mapName,
      })
      return
    }

    toast.error("Failed to copy map name", {
      description: mapName,
    })
  }

  const handleContextMenu = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setMenuOpen(true)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLAnchorElement>) => {
    if (
      event.key === "ContextMenu" ||
      (event.shiftKey && event.key === "F10")
    ) {
      event.preventDefault()
      event.stopPropagation()
      setMenuOpen(true)
    }
  }

  return (
    <DropdownMenu modal={false} open={menuOpen} onOpenChange={setMenuOpen}>
      <div className="relative inline-block" data-drag-scroll-ignore>
        <DropdownMenuTrigger asChild>
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 block"
          />
        </DropdownMenuTrigger>
        <Link
          to="/maps/$mapName/maptop"
          params={mapParams}
          className="inline-block rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          onClick={(event) => {
            event.stopPropagation()
          }}
          onContextMenu={handleContextMenu}
          onKeyDown={handleKeyDown}
        >
          <div
            className={cn(
              "relative h-10 w-56 overflow-hidden rounded-md bg-gray-100 transition-opacity hover:opacity-95 dark:bg-gray-800",
              className,
            )}
            style={
              resolvedImageUrls.length > 0
                ? {
                    backgroundImage: resolvedImageUrls
                      .map((url) => `url("${url.replace(/"/g, "%22")}")`)
                      .join(", "),
                    backgroundPosition: "center",
                    backgroundSize: "cover",
                  }
                : undefined
            }
          >
            <span className="absolute inset-0 flex items-center justify-center bg-black/30 px-2 py-1 text-sm font-medium text-white drop-shadow-lg [text-shadow:_0_1px_2px_rgb(0_0_0_/_0.8)]">
              {mapName}
            </span>
          </div>
        </Link>
      </div>
      <DropdownMenuContent align="start" side="right" sideOffset={10}>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            void handleCopyMapName()
          }}
        >
          <Copy />
          Copy Map Name
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault()
            handleGoToMapPage()
          }}
        >
          <MapIcon />
          Goto Map Page
        </DropdownMenuItem>
        {contextMenuItems ? <DropdownMenuSeparator /> : null}
        {contextMenuItems}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
