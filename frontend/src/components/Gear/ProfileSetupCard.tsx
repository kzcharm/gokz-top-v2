import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { type HardwarePublic, ProductsService } from "@/client"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { PC_COMPONENTS, PERIPHERALS } from "./gear-utils"
import { ProductLink } from "./ProductLink"

function HardwareDetails({ item }: { item: HardwarePublic }) {
  return (
    <dd className="min-w-0 break-words">
      {item.product ? <ProductLink product={item.product} /> : null}
      <div className="text-sm text-muted-foreground">
        {[
          item.storage_capacity_gb
            ? `${item.storage_capacity_gb / (item.storage_capacity_unit === "TB" ? 1000 : 1)} ${item.storage_capacity_unit ?? "GB"}`
            : null,
          item.memory_capacity_gb ? `${item.memory_capacity_gb} GB` : null,
          item.memory_type,
          item.memory_speed_mts ? `${item.memory_speed_mts} MHz` : null,
          item.monitor_size_inches
            ? `${Number(item.monitor_size_inches)}″`
            : null,
          item.monitor_refresh_hz
            ? `${Number(item.monitor_refresh_hz)} Hz`
            : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </div>
    </dd>
  )
}

export function ProfileSetupCard({
  identifier,
  isOwner,
}: {
  identifier: string
  isOwner: boolean
}) {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["setup", "player", identifier],
    queryFn: () => ProductsService.readPlayerSetup({ identifier }),
  })
  if (query.isPending) return <Skeleton className="h-24 w-full" />
  if (query.isError)
    return (
      <Alert>
        <AlertDescription>
          {t("gear.loadError")}{" "}
          <Button variant="ghost" onClick={() => query.refetch()}>
            {t("gear.retry")}
          </Button>
        </AlertDescription>
      </Alert>
    )
  const { hardware, game_settings: game, operating_system } = query.data
  const hasGame = Boolean(game.mouse_dpi || game.sensitivity)
  const empty = hardware.length === 0 && !hasGame && !operating_system
  if (empty && !isOwner) return null
  const gameSection = hasGame ? (
    <section className="flex flex-col gap-3" data-testid="setup-game-settings">
      <h3 className="font-medium">{t("gear.csgo")}</h3>
      <dl className="flex flex-wrap gap-x-6 gap-y-2">
        {[
          [t("gear.dpi"), game.mouse_dpi],
          [t("gear.sensitivity"), game.sensitivity],
          ["eDPI", game.edpi],
        ].map(([label, value]) =>
          value != null ? (
            <div key={String(label)}>
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="font-mono">
                {String(value)
                  .replace(/(\.\d*?)0+$/, "$1")
                  .replace(/\.$/, "")}
              </dd>
            </div>
          ) : null,
        )}
      </dl>
    </section>
  ) : null
  return (
    <Card data-testid="profile-setup">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>{t("gear.setup")}</CardTitle>
        {isOwner ? (
          <Button variant="outline" asChild>
            <Link to="/settings/setup">
              {empty ? t("gear.addSetup") : t("gear.editSetup")}
            </Link>
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="grid items-start gap-6 sm:grid-cols-2">
        {[
          { title: "peripherals", categories: PERIPHERALS },
          { title: "pc", categories: PC_COMPONENTS },
        ].map(({ title, categories }) => {
          const items = categories.flatMap((category) =>
            hardware.filter((item) => item.category === category),
          )
          const hasHardware =
            items.length > 0 || (title === "pc" && operating_system)
          if (!hasHardware && !(title === "peripherals" && hasGame)) return null
          return (
            <div
              key={title}
              className="flex min-w-0 flex-col gap-5"
              data-testid={`setup-${title}`}
            >
              {hasHardware ? (
                <section className="flex flex-col gap-3">
                  <h3 className="font-medium">
                    {t(`gear.${title as "peripherals" | "pc"}`)}
                  </h3>
                  <dl className="flex flex-col gap-2.5">
                    {title === "pc" && operating_system ? (
                      <div className="grid gap-x-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                        <dt className="pt-0.5 text-xs text-muted-foreground">
                          {t("gear.operatingSystem")}
                        </dt>
                        <dd>{operating_system}</dd>
                      </div>
                    ) : null}
                    {items.map((item, index) => (
                      <div
                        key={`${item.category}-${index}`}
                        className="grid gap-x-3 sm:grid-cols-[7rem_minmax(0,1fr)]"
                        data-hardware={item.category}
                      >
                        <dt className="pt-0.5 text-xs text-muted-foreground">
                          {t(`gear.categories.${item.category}`)}
                        </dt>
                        <HardwareDetails item={item} />
                      </div>
                    ))}
                  </dl>
                </section>
              ) : null}
              {title === "peripherals" ? gameSection : null}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
