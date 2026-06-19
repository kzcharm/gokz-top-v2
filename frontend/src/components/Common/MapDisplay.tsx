import { Link, useNavigate } from "@tanstack/react-router"
import { Copy, Download, MapIcon, MessageSquarePlus } from "lucide-react"
import type { KeyboardEvent, MouseEvent, ReactNode } from "react"
import { useState } from "react"
import { toast } from "sonner"

import { MapsService } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import useAuth from "@/hooks/useAuth"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import { getMapDownloadUrlForMapName } from "@/lib/map-downloads"
import { cn } from "@/lib/utils"
import { MapReviewDialog } from "../Reviews/MapReviewDialog"

interface MapDisplayProps {
  mapName: string | null | undefined
  className?: string
  containerClassName?: string
  contextMenuItems?: ReactNode
  downloadUrl?: string | null
  imageUrls?: string[]
  mapId?: number | null
}

interface MapNameContextMenuProps {
  children: (handlers: {
    onContextMenu: (event: MouseEvent<HTMLElement>) => void
    onKeyDown: (event: KeyboardEvent<HTMLElement>) => void
  }) => ReactNode
  contextMenuItems?: ReactNode
  downloadUrl?: string | null
  mapName: string | null | undefined
  mapId?: number | null
}

function stopMenuPropagation(event: MouseEvent | KeyboardEvent) {
  event.stopPropagation()
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

export function MapNameContextMenu({
  children,
  contextMenuItems,
  downloadUrl,
  mapId,
  mapName,
}: MapNameContextMenuProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [reviewTarget, setReviewTarget] = useState<{
    mapId: number
    mapName: string
  } | null>(null)
  const [reviewDialogOpen, setReviewDialogOpen] = useState(false)
  const [, copyToClipboard] = useCopyToClipboard()
  const navigate = useNavigate()
  const { user: currentUser } = useAuth()

  if (!mapName || mapName.trim() === "") {
    return <>{children({ onContextMenu: () => {}, onKeyDown: () => {} })}</>
  }

  const mapParams = { mapName }
  const resolvedDownloadUrl = getMapDownloadUrlForMapName(mapName, downloadUrl)

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

  const handleDownloadMap = () => {
    if (!resolvedDownloadUrl) {
      return
    }

    window.open(resolvedDownloadUrl, "_blank", "noopener,noreferrer")
  }

  const handleAddReview = async () => {
    try {
      let resolvedMapId = mapId ?? null
      if (resolvedMapId === null) {
        const maps = await MapsService.readMaps({ name: mapName })
        resolvedMapId = maps[0]?.id ?? null
      }

      if (resolvedMapId === null) {
        toast.error("Failed to open review", {
          description: mapName,
        })
        return
      }

      setReviewTarget({ mapId: resolvedMapId, mapName })
      setReviewDialogOpen(true)
      setMenuOpen(false)
    } catch {
      toast.error("Failed to open review", {
        description: mapName,
      })
    }
  }

  const handleContextMenu = (event: MouseEvent<HTMLElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setMenuOpen(true)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
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
    <>
      <DropdownMenu modal={false} open={menuOpen} onOpenChange={setMenuOpen}>
        <div className="relative inline-block min-w-0" data-drag-scroll-ignore>
          <DropdownMenuTrigger asChild>
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 block"
            />
          </DropdownMenuTrigger>
          {children({
            onContextMenu: handleContextMenu,
            onKeyDown: handleKeyDown,
          })}
        </div>
        <DropdownMenuContent
          align="start"
          side="right"
          sideOffset={10}
          onClick={stopMenuPropagation}
          onKeyDown={stopMenuPropagation}
        >
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault()
              setMenuOpen(false)
              void handleCopyMapName()
            }}
          >
            <Copy />
            Copy Name
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault()
              setMenuOpen(false)
              handleGoToMapPage()
            }}
          >
            <MapIcon />
            Goto Page
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!resolvedDownloadUrl}
            onSelect={(event) => {
              event.preventDefault()
              setMenuOpen(false)
              handleDownloadMap()
            }}
          >
            <Download />
            Download
          </DropdownMenuItem>
          {currentUser ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={(event) => {
                  event.preventDefault()
                  void handleAddReview()
                }}
              >
                <MessageSquarePlus />
                Add Review
              </DropdownMenuItem>
            </>
          ) : null}
          {contextMenuItems ? <DropdownMenuSeparator /> : null}
          {contextMenuItems}
        </DropdownMenuContent>
      </DropdownMenu>
      {reviewTarget ? (
        <MapReviewDialog
          open={reviewDialogOpen}
          onOpenChange={(nextOpen) => {
            setReviewDialogOpen(nextOpen)
            if (!nextOpen) {
              setReviewTarget(null)
            }
          }}
          mapId={reviewTarget.mapId}
          mapName={reviewTarget.mapName}
        />
      ) : null}
    </>
  )
}

export function MapDisplay({
  mapName,
  className,
  containerClassName,
  contextMenuItems,
  downloadUrl,
  imageUrls,
  mapId,
}: MapDisplayProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [reviewTarget, setReviewTarget] = useState<{
    mapId: number
    mapName: string
  } | null>(null)
  const [reviewDialogOpen, setReviewDialogOpen] = useState(false)
  const [, copyToClipboard] = useCopyToClipboard()
  const navigate = useNavigate()
  const { user: currentUser } = useAuth()

  if (!mapName || mapName.trim() === "") {
    return <span className="text-muted-foreground">-</span>
  }

  const resolvedImageUrls =
    imageUrls && imageUrls.length > 0 ? imageUrls : getMapImageUrls(mapName)
  const mapParams = { mapName }
  const resolvedDownloadUrl = getMapDownloadUrlForMapName(mapName, downloadUrl)

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

  const handleDownloadMap = () => {
    if (!resolvedDownloadUrl) {
      return
    }

    window.open(resolvedDownloadUrl, "_blank", "noopener,noreferrer")
  }

  const handleAddReview = async () => {
    try {
      let resolvedMapId = mapId ?? null
      if (resolvedMapId === null) {
        const maps = await MapsService.readMaps({ name: mapName })
        resolvedMapId = maps[0]?.id ?? null
      }

      if (resolvedMapId === null) {
        toast.error("Failed to open review", {
          description: mapName,
        })
        return
      }

      setReviewTarget({ mapId: resolvedMapId, mapName })
      setReviewDialogOpen(true)
      setMenuOpen(false)
    } catch {
      toast.error("Failed to open review", {
        description: mapName,
      })
    }
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
    <>
      <DropdownMenu modal={false} open={menuOpen} onOpenChange={setMenuOpen}>
        <div
          className={cn("relative inline-block", containerClassName)}
          data-drag-scroll-ignore
        >
          <DropdownMenuTrigger asChild>
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 block"
            />
          </DropdownMenuTrigger>
          <Link
            to="/maps/$mapName/maptop"
            params={mapParams}
            className="block rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
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
        <DropdownMenuContent
          align="start"
          side="right"
          sideOffset={10}
          onClick={stopMenuPropagation}
          onKeyDown={stopMenuPropagation}
        >
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault()
              setMenuOpen(false)
              void handleCopyMapName()
            }}
          >
            <Copy />
            Copy Name
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault()
              setMenuOpen(false)
              handleGoToMapPage()
            }}
          >
            <MapIcon />
            Goto Page
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!resolvedDownloadUrl}
            onSelect={(event) => {
              event.preventDefault()
              setMenuOpen(false)
              handleDownloadMap()
            }}
          >
            <Download />
            Download
          </DropdownMenuItem>
          {currentUser ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={(event) => {
                  event.preventDefault()
                  void handleAddReview()
                }}
              >
                <MessageSquarePlus />
                Add Review
              </DropdownMenuItem>
            </>
          ) : null}
          {contextMenuItems ? <DropdownMenuSeparator /> : null}
          {contextMenuItems}
        </DropdownMenuContent>
      </DropdownMenu>
      {reviewTarget ? (
        <MapReviewDialog
          open={reviewDialogOpen}
          onOpenChange={(nextOpen) => {
            setReviewDialogOpen(nextOpen)
            if (!nextOpen) {
              setReviewTarget(null)
            }
          }}
          mapId={reviewTarget.mapId}
          mapName={reviewTarget.mapName}
        />
      ) : null}
    </>
  )
}
