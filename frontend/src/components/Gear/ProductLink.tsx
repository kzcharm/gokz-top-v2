import { useTranslation } from "react-i18next"
import type { ProductPublic } from "@/client"

export function ProductLink({ product }: { product: ProductPublic }) {
  const { t } = useTranslation()
  const name = `${product.brand} ${product.model}`
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <a
        href={`https://www.google.com/search?q=${encodeURIComponent(name)}`}
        target="_blank"
        rel="noopener noreferrer"
        className="text-left outline-offset-4 hover:text-primary"
        aria-label={t("gear.searchProduct", { product: name })}
      >
        {name}
      </a>
    </span>
  )
}
