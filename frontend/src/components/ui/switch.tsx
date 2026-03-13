import * as React from "react"

import { cn } from "@/lib/utils"

type SwitchProps = Omit<React.ComponentProps<"button">, "onChange"> & {
  checked?: boolean
  defaultChecked?: boolean
  onCheckedChange?: (checked: boolean) => void
}

function Switch({
  checked,
  defaultChecked = false,
  onCheckedChange,
  onClick,
  className,
  disabled,
  type = "button",
  ...props
}: SwitchProps) {
  const [uncontrolledChecked, setUncontrolledChecked] =
    React.useState(defaultChecked)
  const isControlled = checked !== undefined
  const isChecked = isControlled ? checked : uncontrolledChecked

  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (disabled) {
      return
    }

    const nextChecked = !isChecked
    if (!isControlled) {
      setUncontrolledChecked(nextChecked)
    }

    onCheckedChange?.(nextChecked)
    onClick?.(event)
  }

  return (
    <button
      data-slot="switch"
      data-state={isChecked ? "checked" : "unchecked"}
      aria-checked={isChecked}
      className={cn(
        "inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-transparent bg-muted shadow-xs transition-colors outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 data-[state=checked]:bg-green-600 data-[state=checked]:shadow-green-600/25 dark:data-[state=checked]:bg-green-500",
        className,
      )}
      disabled={disabled}
      onClick={handleClick}
      role="switch"
      type={type}
      {...props}
    >
      <span
        aria-hidden="true"
        className={cn(
          "block size-4 rounded-full bg-background shadow-sm ring-1 ring-black/5 transition-transform",
          isChecked ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>
  )
}

export { Switch }
