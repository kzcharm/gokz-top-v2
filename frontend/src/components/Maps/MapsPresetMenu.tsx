import {
  BookmarkIcon,
  ChevronDownIcon,
  RotateCcwIcon,
  SaveIcon,
  Trash2Icon,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { DefaultViewMenuItems } from "@/components/Common/DefaultViewMenuItems"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

const MAX_PRESETS = 20

interface SavedViewPreset<T> {
  id: string
  name: string
  settings: T
}

function readSavedPresets<T>(
  storageKey: string,
  parseSettings: (value: unknown) => T | null,
): SavedViewPreset<T>[] {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) ?? "null")
    if (!value || value.version !== 1 || !Array.isArray(value.presets))
      return []
    return value.presets.slice(-MAX_PRESETS).flatMap((preset: unknown) => {
      if (!preset || typeof preset !== "object") return []
      const item = preset as Record<string, unknown>
      if (
        typeof item.id !== "string" ||
        typeof item.name !== "string" ||
        !item.name.trim()
      )
        return []
      const settings = parseSettings(item.settings)
      return settings ? [{ id: item.id, name: item.name, settings }] : []
    })
  } catch {
    return []
  }
}

function getNextPresetName<T>(presets: SavedViewPreset<T>[]) {
  const usedNumbers = new Set(
    presets.flatMap((preset) => {
      const match = /^Preset (\d+)$/i.exec(preset.name.trim())
      return match ? [Number(match[1])] : []
    }),
  )
  let nextNumber = 1
  while (usedNumbers.has(nextNumber)) {
    nextNumber += 1
  }
  return `Preset ${nextNumber}`
}

export function MapsPresetMenu<T>({
  storageKey,
  currentSettings,
  defaultSettings,
  parseSettings,
  summarize,
  onApply,
}: {
  storageKey: string
  currentSettings: T
  defaultSettings: T
  parseSettings: (value: unknown) => T | null
  summarize: (settings: T) => string
  onApply: (settings: T) => void
}) {
  const { t } = useTranslation()
  const [presets, setPresets] = useState(() =>
    readSavedPresets(storageKey, parseSettings),
  )
  const [menuOpen, setMenuOpen] = useState(false)
  const [saveDialogOpen, setSaveDialogOpen] = useState(false)
  const [presetName, setPresetName] = useState("")

  function writeSavedPresets(nextPresets: SavedViewPreset<T>[]) {
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify({ version: 1, presets: nextPresets }),
      )
      return true
    } catch {
      toast.error(t("maps.presets.saveError"))
      return false
    }
  }

  const handleSave = () => {
    const name = presetName.trim()
    if (!name) {
      return
    }

    const existingPreset = presets.find(
      (preset) => preset.name.toLocaleLowerCase() === name.toLocaleLowerCase(),
    )
    const savedPreset: SavedViewPreset<T> = {
      id:
        existingPreset?.id ??
        `preset-${Date.now()}-${crypto.getRandomValues(new Uint32Array(1))[0]}`,
      name,
      settings: currentSettings,
    }
    const nextPresets = existingPreset
      ? presets.map((preset) =>
          preset.id === existingPreset.id ? savedPreset : preset,
        )
      : [...presets, savedPreset].slice(-MAX_PRESETS)

    if (!writeSavedPresets(nextPresets)) {
      return
    }

    setPresets(nextPresets)
    setPresetName("")
    setSaveDialogOpen(false)
    toast.success(
      t(existingPreset ? "maps.presets.updated" : "maps.presets.saved"),
    )
  }

  const handleDelete = (preset: SavedViewPreset<T>) => {
    const nextPresets = presets.filter((item) => item.id !== preset.id)
    if (!writeSavedPresets(nextPresets)) {
      return
    }

    setPresets(nextPresets)
    toast.success(t("maps.presets.deleted"))
  }

  return (
    <>
      <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9 gap-1.5 bg-background/80 px-2.5"
          >
            <BookmarkIcon data-icon="inline-start" />
            <span>{t("maps.presets.title")}</span>
            <ChevronDownIcon data-icon="inline-end" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuLabel className="text-xs text-muted-foreground">
            {t("maps.presets.heading")}
          </DropdownMenuLabel>
          {presets.length > 0 ? (
            <DropdownMenuGroup className="max-h-72 overflow-y-auto">
              {presets.map((preset) => (
                <div
                  key={preset.id}
                  className="flex items-center gap-1 rounded-sm hover:bg-accent"
                >
                  <DropdownMenuItem asChild>
                    <button
                      type="button"
                      aria-label={t("maps.presets.apply", {
                        name: preset.name,
                      })}
                      className="min-w-0 flex-1 px-2 py-1.5 text-left outline-none"
                      onClick={() => {
                        onApply(preset.settings)
                        setMenuOpen(false)
                      }}
                    >
                      <span className="block truncate text-sm font-medium">
                        {preset.name}
                      </span>
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {summarize(preset.settings)}
                      </span>
                    </button>
                  </DropdownMenuItem>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("maps.presets.delete", { name: preset.name })}
                    title={t("maps.presets.delete", { name: preset.name })}
                    className="mr-1 shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => handleDelete(preset)}
                  >
                    <Trash2Icon />
                  </Button>
                </div>
              ))}
            </DropdownMenuGroup>
          ) : (
            <p className="px-2 py-3 text-xs text-muted-foreground">
              {t("maps.presets.empty")}
            </p>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DefaultViewMenuItems
              storageKey={`${storageKey}.default`}
              currentSettings={currentSettings}
              parseSettings={parseSettings}
            />
            <DropdownMenuItem onSelect={() => onApply(defaultSettings)}>
              <RotateCcwIcon />
              {t("maps.presets.reset")}
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                setPresetName(getNextPresetName(presets))
                setSaveDialogOpen(true)
              }}
            >
              <SaveIcon />
              {t("maps.presets.saveCurrent")}
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("maps.presets.save")}</DialogTitle>
            <DialogDescription>
              {t("maps.presets.description")}
            </DialogDescription>
          </DialogHeader>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              handleSave()
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="maps-preset-name">
                  {t("maps.presets.name")}
                </FieldLabel>
                <Input
                  id="maps-preset-name"
                  aria-label={t("maps.presets.name")}
                  autoFocus
                  maxLength={40}
                  value={presetName}
                  onChange={(event) => setPresetName(event.target.value)}
                  placeholder={t("maps.presets.placeholder")}
                />
              </Field>
            </FieldGroup>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setSaveDialogOpen(false)}
              >
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={presetName.trim().length === 0}>
                <SaveIcon />
                {t("maps.presets.save")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
