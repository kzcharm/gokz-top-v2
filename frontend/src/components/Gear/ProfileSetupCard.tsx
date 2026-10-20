import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { ProductsService } from "@/client"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { PC_COMPONENTS, PERIPHERALS } from "./gear-utils"
import { ProductLink } from "./ProductLink"

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
  const { hardware, game_settings: game } = query.data
  const hasGame = Boolean(game.mouse_dpi || game.sensitivity)
  const empty =
    hardware.length === 0 && !hasGame && !query.data.operating_system
  if (empty && !isOwner) return null
  return (
    <Card>
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
      <CardContent className="grid gap-6 sm:grid-cols-2">
        {[
          { title: "peripherals", categories: PERIPHERALS },
          { title: "pc", categories: PC_COMPONENTS },
        ].map(({ title, categories }) => {
          const items = hardware.filter((item) =>
            categories.includes(item.category),
          )
          return items.length ||
            (title === "pc" && query.data.operating_system) ? (
            <section key={title} className="flex flex-col gap-3">
              <h3 className="font-medium">
                {t(`gear.${title as "peripherals" | "pc"}`)}
              </h3>
              <dl className="flex flex-col gap-3">
                {title === "pc" && query.data.operating_system ? (
                  <div>
                    <dt className="text-xs text-muted-foreground">
                      {t("gear.operatingSystem")}
                    </dt>
                    <dd>{query.data.operating_system}</dd>
                  </div>
                ) : null}
                {items.map((item) => (
                  <div key={item.category}>
                    <dt className="text-xs text-muted-foreground">
                      {t(`gear.categories.${item.category}`)}
                    </dt>
                    <dd>
                      {item.product ? (
                        <ProductLink product={item.product} />
                      ) : null}
                      <div className="text-sm text-muted-foreground">
                        {[
                          item.storage_capacity_gb
                            ? `${item.storage_capacity_gb / (item.storage_capacity_unit === "TB" ? 1000 : 1)} ${item.storage_capacity_unit ?? "GB"}`
                            : null,
                          item.memory_capacity_gb
                            ? `${item.memory_capacity_gb} GB`
                            : null,
                          item.memory_type,
                          item.memory_speed_mts
                            ? `${item.memory_speed_mts} MT/s`
                            : null,
                          item.monitor_refresh_hz
                            ? `${Number(item.monitor_refresh_hz)} Hz`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ) : null
        })}
        {hasGame ? (
          <section className="flex flex-col gap-3 sm:col-span-2">
            <h3 className="font-medium">{t("gear.csgo")}</h3>
            <dl className="flex flex-wrap gap-6">
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
        ) : null}
      </CardContent>
    </Card>
  )
}
