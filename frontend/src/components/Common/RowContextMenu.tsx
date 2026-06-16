"use client"

import {
  createContext,
  type MouseEvent,
  type ReactNode,
  useContext,
  useEffect,
  useRef,
} from "react"
import { createPortal } from "react-dom"
import { cn } from "@/lib/utils"

type RowContextMenuPosition = {
  x: number
  y: number
}

const RowContextMenuCloseContext = createContext<(() => void) | null>(null)

function clampMenuPosition({ x, y }: RowContextMenuPosition) {
  if (typeof window === "undefined") {
    return { x, y }
  }

  return {
    x: Math.max(8, Math.min(x, window.innerWidth - 240)),
    y: Math.max(8, Math.min(y, window.innerHeight - 64)),
  }
}

export function RowContextMenu({
  children,
  onOpenChange,
  open,
  position,
}: {
  children: ReactNode
  onOpenChange: (open: boolean) => void
  open: boolean
  position: RowContextMenuPosition | null
}) {
  const menuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (menuRef.current?.contains(event.target as Node)) {
        return
      }
      onOpenChange(false)
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        onOpenChange(false)
      }
    }

    document.addEventListener("pointerdown", handlePointerDown, true)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown, true)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [onOpenChange, open])

  if (!open || position === null || typeof document === "undefined") {
    return null
  }

  const adjustedPosition = clampMenuPosition(position)

  return createPortal(
    <RowContextMenuCloseContext.Provider value={() => onOpenChange(false)}>
      <div
        ref={menuRef}
        role="menu"
        data-slot="dropdown-menu-content"
        className={cn(
          "fixed z-50 max-h-[min(24rem,calc(100vh-1rem))] min-w-[8rem]",
          "overflow-x-hidden overflow-y-auto rounded-md border bg-popover p-1",
          "text-popover-foreground shadow-md outline-hidden",
        )}
        style={{
          left: adjustedPosition.x,
          top: adjustedPosition.y,
        }}
      >
        {children}
      </div>
    </RowContextMenuCloseContext.Provider>,
    document.body,
  )
}

export function RowContextMenuItem({
  children,
  className,
  disabled,
  onSelect,
  variant = "default",
  ...props
}: Omit<React.ComponentProps<"button">, "onClick" | "type"> & {
  onSelect?: (event: MouseEvent<HTMLButtonElement>) => void
  variant?: "default" | "destructive"
}) {
  const closeMenu = useContext(RowContextMenuCloseContext)

  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      data-variant={variant}
      className={cn(
        "relative flex w-full cursor-default select-none items-center gap-2",
        "rounded-sm px-2 py-1.5 text-left text-sm outline-hidden",
        "focus:bg-accent focus:text-accent-foreground",
        "data-[variant=destructive]:text-destructive data-[variant=destructive]:focus:bg-destructive/10",
        "data-[variant=destructive]:focus:text-destructive data-[variant=destructive]:*:[svg]:!text-destructive",
        "dark:data-[variant=destructive]:focus:bg-destructive/20",
        "disabled:pointer-events-none disabled:opacity-50",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      onClick={(event) => {
        onSelect?.(event)
        if (!event.defaultPrevented) {
          closeMenu?.()
        }
      }}
      {...props}
    >
      {children}
    </button>
  )
}

export function RowContextMenuSeparator({
  className,
  ...props
}: React.ComponentProps<"hr">) {
  return (
    <hr className={cn("-mx-1 my-1 h-px bg-border", className)} {...props} />
  )
}
