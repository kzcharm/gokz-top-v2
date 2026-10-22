import { CheckCircle2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { TROPHY_ASSETS } from "@/components/Common/trophy-assets"
import { Card, CardContent } from "@/components/ui/card"
import { formatNumber, type ProfileTrophyCounts } from "./profile-utils"

function PaddedAverageNumber({ value }: { value: number }) {
  const formattedValue = String(value)
  const paddedValue = formattedValue.padStart(3, "0")

  return <span className="font-mono tabular-nums">{paddedValue}</span>
}

export function CompletionCard({
  title,
  completed,
  total,
  tiers,
  trophies,
  card = false,
}: {
  card?: boolean
  title: string
  completed: number
  total: number
  tiers: Array<{
    label: string
    complete: number
    total: number
    color: string
    averagePoints: number
  }>
  trophies: ProfileTrophyCounts
}) {
  const { t } = useTranslation()
  return (
    <Card
      data-completion-card={card ? "capture" : undefined}
      className="min-w-0 gap-0 rounded-[26px] border-border/70 bg-card/95 py-0"
    >
      <CardContent className="p-6">
        <div className="mx-auto w-full max-w-[36rem] space-y-5">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                {title}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-4">
                {(["gold", "silver", "bronze"] as const).map((trophy) => (
                  <div key={trophy} className="flex items-center gap-2">
                    <img
                      src={TROPHY_ASSETS[trophy]}
                      alt={t("profile.completion.trophyAlt", {
                        trophy: t(`profile.completion.trophies.${trophy}`),
                      })}
                      className="h-7 w-7 object-contain"
                    />
                    <span className="text-2xl font-semibold tracking-tight">
                      {formatNumber(trophies[trophy])}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <p className="text-sm text-muted-foreground md:justify-self-end">
              {formatNumber(completed)} / {formatNumber(total)}
            </p>
          </div>
          <div className="space-y-1.5">
            {tiers.map((tier) => {
              const width = `${tier.total === 0 ? 0 : (tier.complete / tier.total) * 100}%`
              const isTierComplete =
                tier.total > 0 && tier.complete >= tier.total
              return (
                <div
                  key={tier.label}
                  data-completion-tier=""
                  className="grid grid-cols-[88px_minmax(0,1fr)_auto] items-center gap-2 sm:grid-cols-[96px_minmax(0,1fr)_58px] sm:gap-3"
                >
                  <span className="whitespace-nowrap text-right text-[11px] font-semibold leading-4 text-muted-foreground sm:text-xs">
                    {tier.label} ({t("profile.completion.averageShort")}{" "}
                    <PaddedAverageNumber value={tier.averagePoints} />)
                  </span>
                  <div className="h-5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full"
                      style={{ width, backgroundColor: tier.color }}
                    />
                  </div>
                  <span className="flex items-center justify-end gap-1 text-right font-mono text-[11px] tabular-nums text-muted-foreground sm:justify-start sm:text-left sm:text-xs">
                    {tier.complete}/{tier.total}
                    {isTierComplete ? (
                      <CheckCircle2
                        aria-hidden="true"
                        className="size-3 shrink-0"
                        style={{ color: "#22C55E" }}
                      />
                    ) : null}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
