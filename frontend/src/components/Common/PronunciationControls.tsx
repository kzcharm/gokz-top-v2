import { LoaderCircle, Volume2 } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  DropdownMenuGroup,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu"
import {
  type PronunciationTarget,
  usePronunciation,
} from "@/hooks/usePronunciation"
import { PronunciationAdminDialog } from "./PronunciationAdminDialog"

export function PronunciationButton({
  target,
}: {
  target: PronunciationTarget
}) {
  const { t } = useTranslation()
  const { play, loading, playing } = usePronunciation(target)
  const label = t(
    loading ? "mapPronunciation.loading" : "mapPronunciation.play",
  )
  return (
    <>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="shrink-0 rounded-full"
        aria-label={label}
        title={label}
        aria-busy={loading}
        aria-pressed={playing}
        disabled={loading}
        onClick={play}
      >
        {loading ? (
          <LoaderCircle
            className="animate-spin"
            data-icon="inline-start"
            aria-hidden="true"
          />
        ) : (
          <Volume2 data-icon="inline-start" aria-hidden="true" />
        )}
      </Button>
      <PronunciationAdminDialog target={target} />
    </>
  )
}

export function PronunciationMenuItems({
  target,
  closeMenu,
}: {
  target: PronunciationTarget
  closeMenu: () => void
}) {
  const { t } = useTranslation()
  const { play, loading } = usePronunciation(target)
  return (
    <DropdownMenuGroup>
      <DropdownMenuItem
        disabled={loading}
        onSelect={(event) => {
          event.preventDefault()
          closeMenu()
          play()
        }}
      >
        {loading ? <LoaderCircle className="animate-spin" /> : <Volume2 />}
        {t(loading ? "mapPronunciation.loading" : "mapPronunciation.play")}
      </DropdownMenuItem>
      <PronunciationAdminDialog target={target} menu closeMenu={closeMenu} />
    </DropdownMenuGroup>
  )
}
