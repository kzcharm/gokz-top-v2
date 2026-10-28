import { BookmarkCheck, BookmarkX } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import { readDefaultView } from "@/lib/default-view"

export function DefaultViewMenuItems<T>({
  storageKey,
  currentSettings,
  parseSettings,
}: {
  storageKey: string
  currentSettings: T
  parseSettings: (value: unknown) => T | null
}) {
  const { t } = useTranslation()
  const [hasDefault, setHasDefault] = useState(
    () => readDefaultView(storageKey, parseSettings) !== null,
  )

  function updateDefault(clear: boolean) {
    try {
      if (clear) localStorage.removeItem(storageKey)
      else
        localStorage.setItem(
          storageKey,
          JSON.stringify({ version: 1, settings: currentSettings }),
        )
      setHasDefault(!clear)
      toast.success(
        t(clear ? "maps.presets.defaultCleared" : "maps.presets.defaultSaved"),
      )
    } catch {
      toast.error(t("maps.presets.saveError"))
    }
  }

  return (
    <>
      <DropdownMenuItem onSelect={() => updateDefault(false)}>
        <BookmarkCheck />
        {t("maps.presets.setDefault")}
      </DropdownMenuItem>
      {hasDefault ? (
        <DropdownMenuItem onSelect={() => updateDefault(true)}>
          <BookmarkX />
          {t("maps.presets.clearDefault")}
        </DropdownMenuItem>
      ) : null}
    </>
  )
}
