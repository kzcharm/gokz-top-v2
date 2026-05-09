import { BarChart3, Trophy } from "lucide-react"
import { useTranslation } from "react-i18next"

import type { PlayerPublic } from "@/client"
import { Card, CardContent } from "@/components/ui/card"

export function ProfilePlaceholderPanel({
  player,
  activeTab,
}: {
  player: PlayerPublic
  activeTab: "records" | "stats"
}) {
  const { t } = useTranslation()
  return (
    <Card className="gap-0 rounded-[28px] border-border/70 bg-card/95 py-0">
      <CardContent className="grid gap-6 px-6 py-8 md:px-8 md:py-10">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary">
          {activeTab === "records" ? <Trophy /> : <BarChart3 />}
        </div>
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            {t("profile.placeholder.badge")}
          </p>
          <h2 className="text-3xl font-semibold tracking-tight">
            {activeTab === "records"
              ? t("profile.placeholder.recordsHeading", {
                  name: player.alias || player.name,
                })
              : t("profile.placeholder.statsHeading", {
                  name: player.alias || player.name,
                })}
          </h2>
          <p className="max-w-2xl text-sm text-muted-foreground">
            {t("profile.placeholder.description")}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
