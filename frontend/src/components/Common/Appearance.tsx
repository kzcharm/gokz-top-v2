import { Monitor, Moon, Sun } from "lucide-react"
import { useRef, useState } from "react"

import { type Theme, useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

const LONG_PRESS_DELAY_MS = 450

const THEME_OPTIONS: Array<{
  label: string
  testId?: string
  value: Theme
}> = [
  { label: "Light", testId: "light-mode", value: "light" },
  { label: "Dark", testId: "dark-mode", value: "dark" },
  { label: "System", testId: "system-mode", value: "system" },
]

export const Appearance = () => {
  const { resolvedTheme, setTheme, theme } = useTheme()
  const [open, setOpen] = useState(false)
  const longPressTimerRef = useRef<number | null>(null)
  const longPressTriggeredRef = useRef(false)

  const nextTheme = resolvedTheme === "dark" ? "light" : "dark"

  const clearLongPressTimer = () => {
    if (longPressTimerRef.current !== null) {
      window.clearTimeout(longPressTimerRef.current)
      longPressTimerRef.current = null
    }
  }

  const handleThemeToggle = () => {
    setTheme(nextTheme)
    setOpen(false)
  }

  const handleContextMenu = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault()
    clearLongPressTimer()
    longPressTriggeredRef.current = true
    setOpen(true)
  }

  const handlePointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (event.pointerType === "mouse") {
      if (event.button === 0) {
        longPressTriggeredRef.current = false
      }
      return
    }

    clearLongPressTimer()
    longPressTriggeredRef.current = false
    longPressTimerRef.current = window.setTimeout(() => {
      longPressTriggeredRef.current = true
      setOpen(true)
    }, LONG_PRESS_DELAY_MS)
  }

  const handlePointerUp = () => {
    clearLongPressTimer()
  }

  const handlePointerCancel = () => {
    clearLongPressTimer()
  }

  const handleClick = () => {
    if (longPressTriggeredRef.current) {
      longPressTriggeredRef.current = false
      return
    }

    handleThemeToggle()
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (
      event.key === "ContextMenu" ||
      (event.shiftKey && event.key === "F10")
    ) {
      event.preventDefault()
      setOpen(true)
    }
  }

  return (
    <DropdownMenu
      modal={false}
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen)
        if (!nextOpen) {
          longPressTriggeredRef.current = false
        }
      }}
    >
      <div className="relative">
        <DropdownMenuTrigger asChild>
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 block"
          />
        </DropdownMenuTrigger>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="relative text-muted-foreground hover:text-foreground"
          data-testid="theme-button"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={`Toggle to ${nextTheme} mode. Right click for more theme options.`}
          onClick={handleClick}
          onContextMenu={handleContextMenu}
          onKeyDown={handleKeyDown}
          onPointerCancel={handlePointerCancel}
          onPointerDown={handlePointerDown}
          onPointerLeave={handlePointerCancel}
          onPointerUp={handlePointerUp}
        >
          <Sun className="size-[1.2rem] rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute size-[1.2rem] rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          <span className="sr-only">Toggle theme</span>
        </Button>
      </div>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup
          value={theme}
          onValueChange={(value) => setTheme(value as Theme)}
        >
          {THEME_OPTIONS.map((option) => (
            <DropdownMenuRadioItem
              key={option.value}
              value={option.value}
              data-testid={option.testId}
            >
              {option.value === "light" ? <Sun /> : null}
              {option.value === "dark" ? <Moon /> : null}
              {option.value === "system" ? <Monitor /> : null}
              {option.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
