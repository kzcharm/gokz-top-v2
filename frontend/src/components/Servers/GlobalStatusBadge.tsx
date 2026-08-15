import { Check, Globe, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import type { ServerGlobalStatusPublic, ServerPublic } from "@/client"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

const GLOBAL_MODES = ["KZT", "SKZ", "VNL"] as const

function CheckItem({ label, value }: { label: string; value: boolean }) {
  const Icon = value ? Check : X
  return (
    <span className="inline-flex items-center gap-0.5 whitespace-nowrap">
      <span>{label}</span>
      <Icon
        className={cn("h-3 w-3", value ? "text-emerald-400" : "text-red-400")}
        aria-label={value ? "passed" : "failed"}
      />
    </span>
  )
}

function GlobalStatusDetails({
  status,
}: {
  status: ServerGlobalStatusPublic | null
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-1 text-xs">
      <div className="flex items-center gap-1">
        <CheckItem
          label={t("serverGlobalStatus.apiKey")}
          value={status?.api_key_valid ?? false}
        />
        <span>|</span>
        <CheckItem
          label={t("serverGlobalStatus.plugins")}
          value={status?.plugins_valid ?? false}
        />
        <span>|</span>
        <CheckItem
          label={t("serverGlobalStatus.settingsEnforcer")}
          value={status?.settings_enforcer_valid ?? false}
        />
        <span>|</span>
        <CheckItem
          label={t("serverGlobalStatus.map")}
          value={status?.map_valid ?? false}
        />
      </div>
      <div className="flex items-center gap-1">
        {GLOBAL_MODES.map((mode, index) => (
          <span className="inline-flex items-center gap-1" key={mode}>
            {index > 0 && <span>|</span>}
            <CheckItem label={mode} value={status?.modes?.[mode] ?? false} />
          </span>
        ))}
      </div>
    </div>
  )
}

export function GlobalStatusBadge({ server }: { server: ServerPublic }) {
  const { t } = useTranslation()
  const liveStatus = server.live_status
  const status = liveStatus?.global_status ?? null
  if (!liveStatus?.state?.last_plugin_seen_at || !status) {
    return null
  }
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
            "absolute bottom-2 left-2 z-10 inline-flex items-center rounded-md p-1.5 text-white outline-none focus-visible:ring-2 focus-visible:ring-white/80",
            eligible ? "bg-emerald-500" : "bg-red-500",
          )}
        >
          <Globe className="h-4 w-4" />
        </span>
      </TooltipTrigger>
      <TooltipContent sideOffset={6} className="max-w-none">
        <GlobalStatusDetails status={status} />
      </TooltipContent>
    </Tooltip>
  )
}
