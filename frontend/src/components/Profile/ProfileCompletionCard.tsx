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
  compact = false,
}: {
  compact?: boolean
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
      <CardContent className={compact ? "p-3" : "p-6"}>
        <div className={compact ? "w-full space-y-2" : "w-full space-y-5"}>
          <div
            data-completion-summary=""
            className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end"
          >
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                {title}
              </p>
              <div
                className={
                  compact
                    ? "mt-2 flex flex-wrap items-center gap-3"
                    : "mt-3 flex flex-wrap items-center gap-4"
                }
              >
                {(["gold", "silver", "bronze"] as const).map((trophy) => (
                  <div key={trophy} className="flex items-center gap-2">
                    <img
                      src={TROPHY_ASSETS[trophy]}
                      alt={t("profile.completion.trophyAlt", {
                        trophy: t(`profile.completion.trophies.${trophy}`),
                      })}
                      className={
                        compact
                          ? "h-4 w-4 object-contain"
                          : "h-7 w-7 object-contain"
                      }
                    />
                    <span
                      className={
                        compact
                          ? "text-sm font-semibold"
                          : "text-2xl font-semibold tracking-tight"
                      }
                    >
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
          <div
            data-completion-tiers=""
            className="grid grid-cols-[max-content_minmax(0,1fr)_max-content] gap-x-2 gap-y-1.5 sm:gap-x-3"
          >
            {tiers.map((tier) => {
              const width = `${tier.total === 0 ? 0 : (tier.complete / tier.total) * 100}%`
              const isTierComplete =
                tier.total > 0 && tier.complete >= tier.total
              return (
                <div
                  key={tier.label}
                  data-completion-tier=""
                  className="col-span-3 grid grid-cols-subgrid items-center"
                >
                  <span className="whitespace-nowrap text-left text-[11px] font-semibold leading-4 text-muted-foreground sm:text-xs">
                    {tier.label} ({t("profile.completion.averageShort")}{" "}
                    <PaddedAverageNumber value={tier.averagePoints} />)
                  </span>
                  <div
                    className={`${compact ? "h-2.5" : "h-5"} overflow-hidden rounded-full bg-muted`}
                  >
                    <div
                      className="h-full rounded-full"
                      style={{ width, backgroundColor: tier.color }}
                    />
                  </div>
                  <span className="flex items-center justify-end gap-1 text-right font-mono text-[11px] tabular-nums text-muted-foreground sm:justify-start sm:text-left sm:text-xs">
                    {tier.complete}/{tier.total}
                    {isTierComplete && !card ? (
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
