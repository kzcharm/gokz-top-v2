import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  getJumpstatTypeLabel,
  JUMPSTAT_TYPE_OPTIONS,
} from "./jumpstats-columns"

type JumpstatTypeOption = (typeof JUMPSTAT_TYPE_OPTIONS)[number]

export function JumpstatTypeButtons({
  value,
  onValueChange,
}: {
  value: string
  onValueChange: (value: JumpstatTypeOption) => void
}) {
  const { t } = useTranslation()

  return (
    <fieldset
      aria-label={t("leaderboards.jumpstats.jumpType")}
      className="flex min-w-0 flex-1 flex-wrap gap-2"
    >
      {JUMPSTAT_TYPE_OPTIONS.map((option) => (
        <Button
          key={option}
          type="button"
          size="sm"
          variant={value === option ? "default" : "outline"}
          aria-pressed={value === option}
          onClick={() => onValueChange(option)}
        >
          {getJumpstatTypeLabel(option, t)}
        </Button>
      ))}
    </fieldset>
  )
}
