import { Globe } from "lucide-react"

import { cn } from "@/lib/utils"

export type ValidationStatusIconButtonStatus = "validated" | "invalid"

export function ValidationStatusIconButton({
  status,
  label,
  pressed,
  disabled = false,
  onClick,
}: {
  status: ValidationStatusIconButtonStatus
  label: string
  pressed?: boolean
  disabled?: boolean
  onClick: () => void
}) {
  const isValidated = status === "validated"

  return (
    <button
      type="button"
      className={cn(
        "relative inline-flex size-8 items-center justify-center overflow-hidden rounded-md text-white shadow-xs transition-[background-color,box-shadow,transform] duration-300 ease-out outline-none hover:scale-105 active:scale-95 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
        isValidated ? "bg-emerald-500" : "bg-red-500",
      )}
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      title={label}
    >
      <span
        key={status}
        aria-hidden="true"
        className={cn(
          "absolute inset-0 rounded-md opacity-35 motion-safe:animate-ping",
          isValidated ? "bg-emerald-300" : "bg-red-300",
        )}
      />
      <Globe
        className={cn(
          "relative size-4 transform-gpu transition-transform duration-300 ease-out",
          isValidated ? "rotate-0 scale-100" : "rotate-180 scale-90",
        )}
        aria-hidden="true"
      />
    </button>
  )
}
