import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { X } from "lucide-react"
import { useEffect, useId, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  type ProductCategory,
  type ProductPublic,
  ProductsService,
} from "@/client"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { BrandSelector } from "./BrandSelector"

export function ProductSelector({
  category,
  product,
  onChange,
}: {
  category: ProductCategory
  product: ProductPublic | null
  onChange: (product: ProductPublic | null) => void
}) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const id = useId()
  const container = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const dismiss = (event: Event) => {
      if (!container.current?.contains(event.target as Node)) setExpanded(false)
    }
    document.addEventListener("pointerdown", dismiss)
    document.addEventListener("focusin", dismiss)
    return () => {
      document.removeEventListener("pointerdown", dismiss)
      document.removeEventListener("focusin", dismiss)
    }
  }, [])
  const [query, setQuery] = useState("")
  const [search, setSearch] = useState("")
  const [expanded, setExpanded] = useState(false)
  const [active, setActive] = useState(0)
  const [custom, setCustom] = useState(false)
  const [brand, setBrand] = useState("")
  const [otherBrand, setOtherBrand] = useState(false)
  const [productUrl, setProductUrl] = useState("")
  const brands = useQuery({
    queryKey: ["product-brands", category],
    queryFn: () => ProductsService.readProductBrands({ category }),
    enabled: custom,
  })
  let validUrl = !productUrl
  try {
    const parsed = new URL(productUrl)
    validUrl = ["http:", "https:"].includes(parsed.protocol)
  } catch {
    /* Empty input is optional; other invalid URLs disable submission. */
  }
  const [model, setModel] = useState("")
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(query)
      setActive(0)
    }, 200)
    return () => clearTimeout(timer)
  }, [query])
  const results = useQuery({
    queryKey: ["products", category, search],
    queryFn: () => ProductsService.searchProducts({ category, q: search }),
    enabled: expanded,
  })
  const matches = useQuery({
    queryKey: ["products", category, brand, model],
    queryFn: () =>
      ProductsService.searchProducts({
        category,
        q: `${brand} ${model}`.trim(),
        limit: 5,
      }),
    enabled: custom && Boolean(brand.trim() || model.trim()),
  })
  const create = useMutation({
    mutationFn: () =>
      ProductsService.createProduct({
        requestBody: {
          category,
          brand,
          model,
          product_url: productUrl || null,
        },
      }),
    onSuccess: (created) => {
      onChange(created)
      setCustom(false)
      setExpanded(false)
      setQuery("")
      void client.invalidateQueries({ queryKey: ["products"] })
    },
  })
  const select = (item: ProductPublic) => {
    if (item.category !== category) return
    onChange(item)
    setExpanded(false)
    setQuery("")
  }
  return (
    <div ref={container} className="relative flex min-w-0 flex-col gap-3">
      <Label htmlFor={id} className="leading-snug">
        {t(`gear.categories.${category}`)}
      </Label>
      <div className="relative">
        <Input
          id={id}
          className="pr-10"
          value={query || (product ? `${product.brand} ${product.model}` : "")}
          placeholder={t("gear.search")}
          role="combobox"
          aria-expanded={expanded}
          aria-controls={`${id}-results`}
          aria-autocomplete="list"
          aria-activedescendant={
            expanded && results.data?.data[active]
              ? `${id}-${active}`
              : undefined
          }
          onFocus={() => setExpanded(true)}
          onClick={() => setExpanded(true)}
          onChange={(event) => {
            onChange(null)
            setQuery(event.target.value)
            setExpanded(true)
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") setExpanded(false)
            if (event.key === "ArrowDown") {
              event.preventDefault()
              setExpanded(true)
              setActive((value) =>
                Math.min(value + 1, (results.data?.data.length ?? 1) - 1),
              )
            }
            if (event.key === "ArrowUp") {
              event.preventDefault()
              setActive((value) => Math.max(0, value - 1))
            }
            if (event.key === "Enter" && expanded) {
              event.preventDefault()
              const item = results.data?.data[active]
              if (item) select(item)
            }
          }}
        />
        {product || query ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute right-1 top-1/2 size-7 -translate-y-1/2"
            aria-label={t("gear.clearProduct", {
              category: t(`gear.categories.${category}`),
            })}
            onClick={() => {
              onChange(null)
              setQuery("")
              setExpanded(false)
            }}
          >
            <X className="size-4" />
          </Button>
        ) : null}
      </div>
      {expanded ? (
        <div className="flex flex-col gap-2 rounded-md border p-2">
          {results.isLoading ? <p>{t("common.loading")}</p> : null}
          {results.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{t("gear.loadError")}</AlertDescription>
            </Alert>
          ) : null}
          <div
            id={`${id}-results`}
            role="listbox"
            aria-label={t(`gear.categories.${category}`)}
            className="max-h-48 overflow-y-auto"
          >
            {results.data?.data.map((item, index) => (
              <div
                id={`${id}-${index}`}
                key={item.id}
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => select(item)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    select(item)
                  }
                }}
                tabIndex={0}
                className="cursor-pointer rounded px-2 py-2 hover:bg-accent aria-selected:bg-accent"
              >
                {item.brand} {item.model}
              </div>
            ))}
          </div>
          {!results.isLoading && results.data?.count === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("gear.noResults")}
            </p>
          ) : null}
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setModel(query)
              create.reset()
              setExpanded(false)
              setCustom(true)
            }}
          >
            {t("gear.addCustom")}
          </Button>
        </div>
      ) : null}
      <Dialog open={custom} onOpenChange={setCustom}>
        <DialogContent
          aria-describedby={undefined}
          className="max-h-[90dvh] overflow-y-auto"
        >
          <DialogHeader>
            <DialogTitle>{t("gear.addCustom")}</DialogTitle>
          </DialogHeader>
          <Label htmlFor={`${id}-category`}>
            {t("gear.gearType")}{" "}
            <span className="text-destructive" aria-hidden="true">
              *
            </span>
          </Label>
          <Input
            id={`${id}-category`}
            aria-required="true"
            value={t(`gear.categories.${category}`)}
            readOnly
          />
          <Label htmlFor={`${id}-brand`}>
            {t("gear.brand")}{" "}
            <span className="text-destructive" aria-hidden="true">
              *
            </span>
          </Label>
          <BrandSelector
            id={`${id}-brand`}
            brands={brands.data ?? []}
            value={otherBrand ? "__other__" : brand}
            onChange={(value) => {
              setOtherBrand(value === "__other__")
              setBrand(value === "__other__" ? "" : value)
            }}
          />

          {brands.isError ? <p role="alert">{t("gear.loadError")}</p> : null}
          {otherBrand ? (
            <>
              <Label htmlFor={`${id}-custom-brand`}>
                {t("gear.customBrand")}{" "}
                <span className="text-destructive" aria-hidden="true">
                  *
                </span>
              </Label>
              <Input
                id={`${id}-custom-brand`}
                aria-required="true"
                maxLength={100}
                value={brand}
                onChange={(event) => setBrand(event.target.value)}
              />
            </>
          ) : null}
          <Label htmlFor={`${id}-model`}>
            {t("gear.model")}{" "}
            <span className="text-destructive" aria-hidden="true">
              *
            </span>
          </Label>
          <Input
            id={`${id}-model`}
            aria-required="true"
            maxLength={200}
            value={model}
            onChange={(event) => setModel(event.target.value)}
          />
          <Label htmlFor={`${id}-url`}>{t("gear.productUrl")}</Label>
          <Input
            id={`${id}-url`}
            type="url"
            maxLength={2048}
            placeholder="https://"
            value={productUrl}
            aria-invalid={!validUrl}
            onChange={(event) => setProductUrl(event.target.value)}
          />

          {!validUrl ? <p role="alert">{t("gear.invalidUrl")}</p> : null}
          {matches.data?.data.some((item) => item.category === category) ? (
            <div className="flex flex-col gap-2">
              <p>{t("gear.possibleMatches")}</p>
              {matches.data.data
                .filter((item) => item.category === category)
                .map((item) => (
                  <Button
                    key={item.id}
                    type="button"
                    variant="outline"
                    onClick={() => {
                      select(item)
                      setCustom(false)
                    }}
                  >
                    {item.brand} {item.model}
                  </Button>
                ))}
            </div>
          ) : null}
          {create.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{t("gear.createError")}</AlertDescription>
            </Alert>
          ) : null}
          <Button
            type="button"
            disabled={
              !brand.trim() || !model.trim() || !validUrl || create.isPending
            }
            onClick={() => create.mutate()}
          >
            {t("gear.addAndSelect")}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}
