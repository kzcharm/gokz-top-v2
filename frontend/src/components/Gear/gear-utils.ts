import type { ProductCategory } from "@/client"

export const PERIPHERALS: ProductCategory[] = [
  "monitor",
  "mouse",
  "mouse_pad",
  "keyboard",
  "headset",
]
export const PC_COMPONENTS: ProductCategory[] = [
  "cpu",
  "gpu",
  "memory",
  "motherboard",
  "storage",
  "power_supply",
  "case",
  "cooling",
]
export const CATEGORIES = [...PERIPHERALS, ...PC_COMPONENTS]

// Integer arithmetic avoids rounding drift and matches the API's six-place decimal input.
export function calculateEdpi(dpi: string, sensitivity: string): string | null {
  if (
    !/^[1-9]\d*$/.test(dpi) ||
    !/^(?:\d+(?:\.\d{0,6})?|\.\d{1,6})$/.test(sensitivity)
  )
    return null
  const [whole, fraction = ""] = sensitivity.split(".")
  const scaled =
    BigInt(whole || "0") * 1_000_000n + BigInt(fraction.padEnd(6, "0"))
  if (scaled <= 0n) return null
  const value = BigInt(dpi) * scaled
  const remainder = (value % 1_000_000n)
    .toString()
    .padStart(6, "0")
    .replace(/0+$/, "")
  return `${value / 1_000_000n}${remainder ? `.${remainder}` : ""}`
}
