import { Settings } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useGlobalPreferences } from "@/components/global-preferences-provider"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import useAuth from "@/hooks/useAuth"

export function GlobalPreferences() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { showHiddenMaps, setShowHiddenMaps } = useGlobalPreferences()
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-foreground"
          aria-label={t("preferences.quickSettings")}
        >
          <Settings className="size-[1.2rem]" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuCheckboxItem
          checked={!!user && showHiddenMaps}
          disabled={!user}
          onCheckedChange={setShowHiddenMaps}
        >
          {t("profile.hiddenMaps.showToggle")}
        </DropdownMenuCheckboxItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
