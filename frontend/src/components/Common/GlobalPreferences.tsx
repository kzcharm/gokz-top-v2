import { ChevronRight, EyeOff, Settings, Timer, Type } from "lucide-react"
import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useGlobalPreferences } from "@/components/global-preferences-provider"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import useAuth from "@/hooks/useAuth"
import {
  RUN_TIME_FONT_FAMILIES,
  RUN_TIME_FONT_NAMES,
  type RunTimeFont,
} from "@/lib/run-time"

const toggleClassName =
  "min-h-10 rounded-md py-2 pl-2.5 pr-9 [&>span:first-child]:left-auto [&>span:first-child]:right-2.5 [&>span:first-child]:size-4 [&>span:first-child]:rounded [&>span:first-child]:border [&>span:first-child]:border-input"

export function GlobalPreferences() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [fontDialogOpen, setFontDialogOpen] = useState(false)
  const gearButtonRef = useRef<HTMLButtonElement>(null)
  const {
    showHiddenMaps,
    setShowHiddenMaps,
    showMilliseconds,
    setShowMilliseconds,
    runTimeFont,
    setRunTimeFont,
  } = useGlobalPreferences()
  return (
    <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button
            ref={gearButtonRef}
            type="button"
            variant="ghost"
            size="icon"
            className="text-muted-foreground hover:text-foreground"
            aria-label={t("preferences.quickSettings")}
          >
            <Settings className="size-[1.2rem]" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          sideOffset={8}
          className="w-80 max-w-[calc(100vw-1rem)] rounded-xl p-1.5"
          onCloseAutoFocus={(event) => {
            if (fontDialogOpen) event.preventDefault()
          }}
        >
          <DropdownMenuLabel>
            <span className="text-xs text-muted-foreground">
              {t("preferences.quickSettings")}
            </span>
          </DropdownMenuLabel>
          <DropdownMenuGroup>
            <DropdownMenuCheckboxItem
              className={toggleClassName}
              checked={!!user && showHiddenMaps}
              disabled={!user}
              onCheckedChange={setShowHiddenMaps}
            >
              <EyeOff aria-hidden="true" />
              {t("profile.hiddenMaps.showToggle")}
            </DropdownMenuCheckboxItem>
            <DropdownMenuCheckboxItem
              className={toggleClassName}
              checked={showMilliseconds}
              onCheckedChange={setShowMilliseconds}
            >
              <Timer aria-hidden="true" />
              {t("maps.options.milliseconds")}
            </DropdownMenuCheckboxItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem
              className="min-h-10 gap-2.5 rounded-md px-2.5 py-2"
              aria-label={t("preferences.runTimeFont")}
              onSelect={() => setFontDialogOpen(true)}
            >
              <Type aria-hidden="true" />
              <span className="min-w-0 flex-1">
                {t("preferences.runTimeFont")}
              </span>
              <span className="max-w-24 shrink-0 truncate text-xs text-muted-foreground">
                {RUN_TIME_FONT_NAMES[runTimeFont]}
              </span>
              <ChevronRight aria-hidden="true" />
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={fontDialogOpen} onOpenChange={setFontDialogOpen}>
        <DialogContent
          className="sm:max-w-md"
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            gearButtonRef.current?.focus()
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("preferences.runTimeFont")}</DialogTitle>
          </DialogHeader>
          <fieldset className="flex flex-col gap-3">
            <legend className="sr-only">{t("preferences.runTimeFont")}</legend>
            {(Object.keys(RUN_TIME_FONT_FAMILIES) as RunTimeFont[]).map(
              (font) => (
                <label
                  key={font}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-4 has-[:checked]:border-primary"
                >
                  <input
                    type="radio"
                    name="run-time-font"
                    value={font}
                    checked={runTimeFont === font}
                    onChange={() => setRunTimeFont(font)}
                    className="mt-1 accent-primary"
                  />
                  <span className="flex min-w-0 flex-col gap-2">
                    <span className="block text-sm font-medium">
                      {RUN_TIME_FONT_NAMES[font]}
                    </span>
                    <span
                      className="run-time block text-sm"
                      style={{ fontFamily: RUN_TIME_FONT_FAMILIES[font] }}
                    >
                      0:09.007 · 1:23.456
                    </span>
                  </span>
                </label>
              ),
            )}
          </fieldset>
        </DialogContent>
      </Dialog>
    </>
  )
}
