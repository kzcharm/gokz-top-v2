import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useId, useState } from "react"
import { createPortal } from "react-dom"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  type HardwareInput,
  type ProductCategory,
  type ProductPublic,
  ProductsService,
  type SetupPublic,
} from "@/client"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  CATEGORIES,
  calculateEdpi,
  PC_COMPONENTS,
  PERIPHERALS,
} from "./gear-utils"
import { ProductSelector } from "./ProductSelector"

function SetupForm({ initial }: { initial: SetupPublic }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const formId = useId()
  const [headerActions, setHeaderActions] = useState<HTMLElement | null>(null)
  useEffect(() => {
    setHeaderActions(document.getElementById("settings-setup-actions"))
  }, [])
  const [selected, setSelected] = useState<
    Partial<Record<ProductCategory, ProductPublic | null>>
  >(() =>
    Object.fromEntries(
      initial.hardware.map((item) => [item.category, item.product ?? null]),
    ),
  )
  const memory = initial.hardware.find((item) => item.category === "memory")
  const storage = initial.hardware.find((item) => item.category === "storage")
  const [storageCapacity, setStorageCapacity] = useState(
    storage?.storage_capacity_gb
      ? String(
          storage.storage_capacity_gb /
            (storage.storage_capacity_unit === "TB" ? 1000 : 1),
        )
      : "",
  )
  const [storageUnit, setStorageUnit] = useState<"GB" | "TB">(
    storage?.storage_capacity_unit ?? "GB",
  )
  const [operatingSystem, setOperatingSystem] = useState(
    initial.operating_system ?? "",
  )
  const monitor = initial.hardware.find((item) => item.category === "monitor")
  const [capacity, setCapacity] = useState(
    String(memory?.memory_capacity_gb ?? ""),
  )
  const [memoryType, setMemoryType] = useState(memory?.memory_type ?? "")
  const [refreshRate, setRefreshRate] = useState(
    monitor?.monitor_refresh_hz ?? "",
  )
  const [dpi, setDpi] = useState(String(initial.game_settings.mouse_dpi ?? ""))
  const [sensitivity, setSensitivity] = useState(
    initial.game_settings.sensitivity
      ?.replace(/(\.\d*?)0+$/, "$1")
      .replace(/\.$/, "") ?? "",
  )
  const edpi = calculateEdpi(dpi, sensitivity)
  const save = useMutation({
    mutationFn: () => {
      const hardware: HardwareInput[] = CATEGORIES.flatMap((category) => {
        const product = selected[category]
        const hasMemory =
          category === "memory" && Boolean(capacity || memoryType)
        const hasStorage = category === "storage" && Boolean(storageCapacity)
        if (!product && !hasMemory && !hasStorage) return []
        return [
          {
            category,
            product_id: product?.id ?? null,
            ...(category === "storage"
              ? {
                  storage_capacity_unit: storageUnit,
                  storage_capacity_gb: storageCapacity
                    ? Math.round(
                        Number(storageCapacity) *
                          (storageUnit === "TB" ? 1000 : 1),
                      )
                    : null,
                }
              : {}),
            ...(category === "memory"
              ? {
                  memory_capacity_gb: capacity ? Number(capacity) : null,
                  memory_type: memoryType || null,
                  memory_speed_mts: memory?.memory_speed_mts ?? null,
                }
              : {}),
            ...(category === "monitor"
              ? { monitor_refresh_hz: refreshRate || null }
              : {}),
          },
        ]
      })
      return ProductsService.saveMySetup({
        requestBody: {
          hardware,
          operating_system: operatingSystem || null,
          game_settings: {
            mouse_dpi: dpi ? Number(dpi) : null,
            sensitivity: sensitivity || null,
          },
        },
      })
    },
    onSuccess: (data) => {
      client.setQueryData(["setup", "me"], data)
      void client.invalidateQueries({ queryKey: ["setup", "player"] })
      void client.invalidateQueries({ queryKey: ["gear-leaderboard"] })
      toast.success(t("gear.saved"))
    },
  })
  return (
    <form
      id={formId}
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      {headerActions
        ? createPortal(
            <Button
              type="submit"
              form={formId}
              disabled={save.isPending || Boolean(dpi && sensitivity && !edpi)}
            >
              {save.isPending ? t("common.loading") : t("common.save")}
            </Button>,
            headerActions,
          )
        : null}
      <fieldset
        disabled={save.isPending}
        className="flex min-w-0 flex-col gap-6"
      >
        {[
          ["peripherals", PERIPHERALS],
          ["pc", PC_COMPONENTS],
        ].map(([group, categories]) => (
          <Card key={group as string}>
            <CardHeader>
              <CardTitle>
                {t(`gear.${group as "peripherals" | "pc"}`)}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <FieldGroup className="grid gap-6 md:grid-cols-2">
                {(categories as ProductCategory[]).map((category) => (
                  <div
                    key={category}
                    data-gear={category}
                    className={
                      category === "memory"
                        ? "grid min-w-0 gap-4 sm:grid-cols-[2fr_1fr_1fr] md:col-span-2"
                        : category === "mouse" ||
                            category === "monitor" ||
                            category === "storage"
                          ? "grid min-w-0 gap-4 sm:grid-cols-[2fr_1fr]"
                          : "min-w-0"
                    }
                  >
                    <ProductSelector
                      category={category}
                      product={selected[category] ?? null}
                      onChange={(product) =>
                        setSelected((current) => ({
                          ...current,
                          [category]: product,
                        }))
                      }
                    />
                    {category === "storage" ? (
                      <Field>
                        <FieldLabel htmlFor="storage-capacity">
                          {t("gear.storageCapacity")}
                        </FieldLabel>
                        <div className="flex min-w-0 gap-2">
                          <Input
                            id="storage-capacity"
                            type="number"
                            min={storageUnit === "TB" ? 0.001 : 1}
                            max={1000000000 / (storageUnit === "TB" ? 1000 : 1)}
                            step={storageUnit === "TB" ? 0.001 : 1}
                            value={storageCapacity}
                            onChange={(event) =>
                              setStorageCapacity(event.target.value)
                            }
                            className="min-w-0"
                          />
                          <Select
                            value={storageUnit}
                            onValueChange={(value: "GB" | "TB") => {
                              if (storageCapacity)
                                setStorageCapacity(
                                  String(
                                    Number(
                                      (
                                        (Number(storageCapacity) *
                                          (storageUnit === "TB" ? 1000 : 1)) /
                                        (value === "TB" ? 1000 : 1)
                                      ).toFixed(3),
                                    ),
                                  ),
                                )
                              setStorageUnit(value)
                            }}
                          >
                            <SelectTrigger
                              aria-label={t("gear.storageUnit")}
                              className="w-20 shrink-0"
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectItem value="GB">GB</SelectItem>
                                <SelectItem value="TB">TB</SelectItem>
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                        </div>
                      </Field>
                    ) : null}
                    {category === "mouse" ? (
                      <Field>
                        <FieldLabel htmlFor="mouse-dpi">
                          {t("gear.dpi")}
                        </FieldLabel>
                        <Input
                          id="mouse-dpi"
                          type="number"
                          min={1}
                          max={2147483647}
                          step={1}
                          value={dpi}
                          onChange={(e) => setDpi(e.target.value)}
                        />
                      </Field>
                    ) : null}
                    {category === "monitor" ? (
                      <Field>
                        <FieldLabel htmlFor="monitor-refresh">
                          {t("gear.monitorRefresh")}
                        </FieldLabel>
                        <Input
                          id="monitor-refresh"
                          type="number"
                          min={0.001}
                          max={10000}
                          step={0.001}
                          disabled={!selected.monitor}
                          value={refreshRate}
                          onChange={(e) => setRefreshRate(e.target.value)}
                        />
                      </Field>
                    ) : null}
                    {category === "memory" ? (
                      <>
                        {" "}
                        <Field>
                          <FieldLabel htmlFor="memory-capacity">
                            {t("gear.memoryCapacity")}
                          </FieldLabel>
                          <Input
                            id="memory-capacity"
                            type="number"
                            min={1}
                            max={1048576}
                            step={1}
                            value={capacity}
                            onChange={(e) => setCapacity(e.target.value)}
                          />
                        </Field>
                        <Field>
                          <FieldLabel htmlFor="memory-type">
                            {t("gear.memoryType")}
                          </FieldLabel>
                          <Select
                            value={memoryType || "none"}
                            onValueChange={(value) =>
                              setMemoryType(value === "none" ? "" : value)
                            }
                          >
                            <SelectTrigger id="memory-type" className="w-full">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectItem value="none">
                                  {t("common.none")}
                                </SelectItem>
                                {[1, 2, 3, 4, 5, 6].map((generation) => (
                                  <SelectItem
                                    key={generation}
                                    value={`DDR${generation}`}
                                  >
                                    DDR{generation}
                                  </SelectItem>
                                ))}
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                        </Field>
                      </>
                    ) : null}
                  </div>
                ))}
              </FieldGroup>
              {group === "pc" ? (
                <Field className="mt-6 sm:max-w-sm">
                  <FieldLabel htmlFor="operating-system">
                    {t("gear.operatingSystem")}
                  </FieldLabel>
                  <Select
                    value={operatingSystem || "none"}
                    onValueChange={(value) =>
                      setOperatingSystem(value === "none" ? "" : value)
                    }
                  >
                    <SelectTrigger id="operating-system" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectItem value="none">{t("common.none")}</SelectItem>
                        {[
                          "Windows 11",
                          "Windows 10",
                          "Windows 8.1",
                          "Windows 7",
                          "Linux",
                          "SteamOS",
                          "macOS",
                          "FreeBSD",
                          "Other",
                        ].map((value) => (
                          <SelectItem key={value} value={value}>
                            {value === "Other" ? t("gear.otherSystem") : value}
                          </SelectItem>
                        ))}
                        {operatingSystem &&
                        ![
                          "Windows 11",
                          "Windows 10",
                          "Windows 8.1",
                          "Windows 7",
                          "Linux",
                          "SteamOS",
                          "macOS",
                          "FreeBSD",
                          "Other",
                        ].includes(operatingSystem) ? (
                          <SelectItem value={operatingSystem}>
                            {operatingSystem}
                          </SelectItem>
                        ) : null}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
              ) : null}
            </CardContent>
          </Card>
        ))}
        <Card>
          <CardHeader>
            <CardTitle>{t("gear.csgo")}</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldGroup className="grid gap-6 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="sensitivity">
                  {t("gear.sensitivity")}
                </FieldLabel>
                <Input
                  id="sensitivity"
                  type="number"
                  min={0.000001}
                  max="999999999999.999999"
                  step={0.000001}
                  value={sensitivity}
                  onChange={(e) => setSensitivity(e.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="edpi">eDPI</FieldLabel>
                <output
                  id="edpi"
                  className="py-2 font-mono text-lg"
                  aria-live="polite"
                >
                  {edpi ?? "—"}
                </output>
                <p className="text-xs text-muted-foreground">
                  {t("gear.edpiFormula")}
                </p>
              </Field>
            </FieldGroup>
          </CardContent>
        </Card>
        {save.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{t("gear.saveError")}</AlertDescription>
          </Alert>
        ) : null}
        <Button
          type="submit"
          className="self-end"
          disabled={save.isPending || Boolean(dpi && sensitivity && !edpi)}
        >
          {save.isPending ? t("common.loading") : t("common.save")}
        </Button>
      </fieldset>
    </form>
  )
}

export function SetupEditor() {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ["setup", "me"],
    queryFn: () => ProductsService.readMySetup(),
  })
  if (query.isPending) return <Skeleton className="h-64 w-full" />
  if (query.isError)
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {t("gear.loadError")}{" "}
          <Button variant="outline" onClick={() => query.refetch()}>
            {t("gear.retry")}
          </Button>
        </AlertDescription>
      </Alert>
    )
  return <SetupForm initial={query.data} />
}
