import {
  BookmarkIcon,
  ChevronDownIcon,
  RotateCcwIcon,
  SaveIcon,
  Trash2Icon,
} from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import type { ModeSelectorValue } from "@/components/Common/ModeSelector"
import type { TierSelectorValue } from "@/components/Common/TierSelector"
import type { PbRecordsSortState } from "@/components/Records/pb-records-utils"
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
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

const PRESET_STORAGE_KEY = "gokz-profile-record-presets-v1"
const MAX_PRESETS = 20

export interface ProfileRecordsViewState {
  mapSearch: string
  selectedMode: ModeSelectorValue
  selectedTier: TierSelectorValue
  selectedStage: number | null
  minTeleports: string
  maxTeleports: string
  minPoints: string
  maxPoints: string
  minRating: string
  maxRating: string
  serverSearch: string
  fromDate: string
  toDate: string
  sort: PbRecordsSortState
}

export const DEFAULT_PROFILE_RECORDS_VIEW_STATE: ProfileRecordsViewState = {
  mapSearch: "",
  selectedMode: "all",
  selectedTier: "all",
  selectedStage: null,
  minTeleports: "",
  maxTeleports: "",
  minPoints: "",
  maxPoints: "",
  minRating: "",
  maxRating: "",
  serverSearch: "",
  fromDate: "",
  toDate: "",
  sort: {
    column: "datetime",
    direction: "desc",
  },
}

export interface ProfileRecordsPresetSettings {
  isProOnly: boolean
  isBonus: boolean
  view: ProfileRecordsViewState
}

interface SavedProfileRecordsPreset {
  id: string
  name: string
  settings: ProfileRecordsPresetSettings
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

function readString(value: unknown) {
  return typeof value === "string" ? value : ""
}

function parseViewState(value: unknown): ProfileRecordsViewState | null {
  if (!isObject(value)) {
    return null
  }

  const mode = value.selectedMode
  const tier = value.selectedTier
  const stage = value.selectedStage
  const sort = value.sort
  const validMode =
    mode === "all" || mode === "KZT" || mode === "SKZ" || mode === "VNL"
  const validTier =
    tier === "all" ||
    tier === "none" ||
    tier === "1" ||
    tier === "2" ||
    tier === "3" ||
    tier === "4" ||
    tier === "5" ||
    tier === "6" ||
    tier === "7" ||
    tier === "8"

  if (
    !validMode ||
    !validTier ||
    !(
      stage === null ||
      (typeof stage === "number" && Number.isFinite(stage))
    ) ||
    !isObject(sort) ||
    ![
      "player",
      "map",
      "mode",
      "tier",
      "stage",
      "tps",
      "time",
      "points",
      "rating",
      "server",
      "datetime",
    ].includes(String(sort.column)) ||
    (sort.direction !== "asc" && sort.direction !== "desc")
  ) {
    return null
  }

  return {
    mapSearch: readString(value.mapSearch),
    selectedMode: mode,
    selectedTier: tier,
    selectedStage: stage,
    minTeleports: readString(value.minTeleports),
    maxTeleports: readString(value.maxTeleports),
    minPoints: readString(value.minPoints),
    maxPoints: readString(value.maxPoints),
    minRating: readString(value.minRating),
    maxRating: readString(value.maxRating),
    serverSearch: readString(value.serverSearch),
    fromDate: readString(value.fromDate),
    toDate: readString(value.toDate),
    sort: {
      column: sort.column as PbRecordsSortState["column"],
      direction: sort.direction,
    },
  }
}

function readSavedPresets(): SavedProfileRecordsPreset[] {
  try {
    const storedValue = window.localStorage.getItem(PRESET_STORAGE_KEY)
    if (!storedValue) {
      return []
    }

    const parsedValue: unknown = JSON.parse(storedValue)
    if (!isObject(parsedValue) || parsedValue.version !== 1) {
      return []
    }

    const presets = Array.isArray(parsedValue.presets)
      ? parsedValue.presets
      : []
    return presets.flatMap((preset) => {
      if (
        !isObject(preset) ||
        typeof preset.id !== "string" ||
        typeof preset.name !== "string" ||
        !isObject(preset.settings) ||
        typeof preset.settings.isProOnly !== "boolean" ||
        typeof preset.settings.isBonus !== "boolean"
      ) {
        return []
      }

      const view = parseViewState(preset.settings.view)
      if (!view) {
        return []
      }

      return [
        {
          id: preset.id,
          name: preset.name,
          settings: {
            isProOnly: preset.settings.isProOnly,
            isBonus: preset.settings.isBonus,
            view,
          },
        },
      ]
    })
  } catch {
    return []
  }
}

function writeSavedPresets(presets: SavedProfileRecordsPreset[]) {
  try {
    window.localStorage.setItem(
      PRESET_STORAGE_KEY,
      JSON.stringify({ version: 1, presets }),
    )
    return true
  } catch {
    toast.error("Could not save presets in this browser.")
    return false
  }
}

function summarizePreset(settings: ProfileRecordsPresetSettings) {
  const type = settings.isProOnly ? "PRO" : "NUB"
  const course = settings.isBonus ? "Bonus" : "Main"
  const sortColumn =
    settings.view.sort.column === "datetime"
      ? "Date"
      : settings.view.sort.column.toUpperCase()
  const direction = settings.view.sort.direction === "desc" ? "down" : "up"
  return `${type} · ${course} · ${sortColumn} ${direction}`
}

function getNextPresetName(presets: SavedProfileRecordsPreset[]) {
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

export function ProfileRecordsPresetMenu({
  currentSettings,
  onApply,
}: {
  currentSettings: ProfileRecordsPresetSettings
  onApply: (settings: ProfileRecordsPresetSettings) => void
}) {
  const [presets, setPresets] = useState(readSavedPresets)
  const [menuOpen, setMenuOpen] = useState(false)
  const [saveDialogOpen, setSaveDialogOpen] = useState(false)
  const [presetName, setPresetName] = useState("")

  const handleSave = () => {
    const name = presetName.trim()
    if (!name) {
      return
    }

    const existingPreset = presets.find(
      (preset) => preset.name.toLocaleLowerCase() === name.toLocaleLowerCase(),
    )
    const savedPreset: SavedProfileRecordsPreset = {
      id: existingPreset?.id ?? window.crypto.randomUUID(),
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
    toast.success(existingPreset ? "Preset updated." : "Preset saved.")
  }

  const handleDelete = (preset: SavedProfileRecordsPreset) => {
    const nextPresets = presets.filter((item) => item.id !== preset.id)
    if (!writeSavedPresets(nextPresets)) {
      return
    }

    setPresets(nextPresets)
    toast.success("Preset deleted.")
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
            <BookmarkIcon />
            <span>Presets</span>
            <ChevronDownIcon className="size-3.5 opacity-50" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuLabel className="text-xs text-muted-foreground">
            Filters &amp; sort presets
          </DropdownMenuLabel>
          {presets.length > 0 ? (
            <div className="max-h-72 overflow-y-auto">
              {presets.map((preset) => (
                <div
                  key={preset.id}
                  className="flex items-center gap-1 rounded-sm hover:bg-accent"
                >
                  <button
                    type="button"
                    aria-label={`Apply preset ${preset.name}`}
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
                      {summarizePreset(preset.settings)}
                    </span>
                  </button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete preset ${preset.name}`}
                    title={`Delete ${preset.name}`}
                    className="mr-1 shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => handleDelete(preset)}
                  >
                    <Trash2Icon />
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="px-2 py-3 text-xs text-muted-foreground">
              No saved presets yet.
            </p>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() =>
              onApply({
                isProOnly: false,
                isBonus: false,
                view: DEFAULT_PROFILE_RECORDS_VIEW_STATE,
              })
            }
          >
            <RotateCcwIcon />
            Reset view
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={() => {
              setPresetName(getNextPresetName(presets))
              setSaveDialogOpen(true)
            }}
          >
            <SaveIcon />
            Save current view
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Save preset</DialogTitle>
            <DialogDescription>
              Save NUB or PRO, bonus mode, filters, and sort order in this
              browser.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              handleSave()
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="profile-records-preset-name">Name</Label>
              <Input
                id="profile-records-preset-name"
                aria-label="Preset name"
                autoFocus
                maxLength={40}
                value={presetName}
                onChange={(event) => setPresetName(event.target.value)}
                placeholder="e.g. Recent PRO runs"
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setSaveDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={presetName.trim().length === 0}>
                <SaveIcon />
                Save preset
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
