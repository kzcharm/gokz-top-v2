import { Check, Globe2, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import type { ServerGlobalStatusPublic, ServerPublic } from "@/client"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

const GLOBAL_MODES = ["KZT", "SKZ", "VNL"] as const

function CheckRow({ label, value }: { label: string; value: boolean }) {
  const Icon = value ? Check : X
  return (
    <div className="flex items-center justify-between gap-5">
      <span>{label}</span>
      <Icon
        className={cn(
          "h-3.5 w-3.5",
          value ? "text-emerald-400" : "text-red-400",
        )}
        aria-label={value ? "passed" : "failed"}
      />
    </div>
  )
}

function GlobalStatusDetails({
  status,
}: {
  status: ServerGlobalStatusPublic | null
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-1.5">
      <div className="mb-2 font-semibold">{t("serverGlobalStatus.title")}</div>
      <CheckRow
        label={t("serverGlobalStatus.apiKey")}
        value={status?.api_key_valid ?? false}
      />
      <CheckRow
        label={t("serverGlobalStatus.plugins")}
        value={status?.plugins_valid ?? false}
      />
      <CheckRow
        label={t("serverGlobalStatus.settingsEnforcer")}
        value={status?.settings_enforcer_valid ?? false}
      />
      <CheckRow
        label={t("serverGlobalStatus.map")}
        value={status?.map_valid ?? false}
      />
      <div className="mt-2 border-t border-white/15 pt-2 font-medium">
        {t("serverGlobalStatus.modes")}
      </div>
      {GLOBAL_MODES.map((mode) => (
        <CheckRow
          key={mode}
          label={mode}
          value={status?.modes?.[mode] ?? false}
        />
      ))}
      <div className="mt-2 border-t border-white/15 pt-2 text-[11px] text-background/70">
        {t("serverGlobalStatus.playerNotEvaluated")}
      </div>
    </div>
  )
}

export function GlobalStatusBadge({ server }: { server: ServerPublic }) {
  const { t } = useTranslation()
  const liveStatus = server.live_status
  const status = liveStatus?.global_status ?? null
  const eligible = Boolean(liveStatus?.is_online && status?.eligible)

  return (
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label={t(
            eligible
              ? "serverGlobalStatus.eligibleAria"
              : "serverGlobalStatus.ineligibleAria",
          )}
          className={cn(
            "absolute bottom-2 left-2 z-10 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-white shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-white/80",
            eligible ? "bg-emerald-500" : "bg-black/60",
          )}
        >
          <Globe2 className="h-3.5 w-3.5" />
          <span>global</span>
        </span>
      </TooltipTrigger>
      <TooltipContent sideOffset={6} className="max-w-64">
        <GlobalStatusDetails status={status} />
      </TooltipContent>
    </Tooltip>
  )
}
