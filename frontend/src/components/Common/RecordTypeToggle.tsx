import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

export function RecordTypeToggle({
  id,
  isProOnly,
  onCheckedChange,
  ariaLabel,
  variant = "switch",
}: {
  id: string
  isProOnly: boolean
  onCheckedChange: (checked: boolean) => void
  ariaLabel?: string
  variant?: "switch" | "button"
}) {
  if (variant === "button")
    return (
      <Button
        id={id}
        type="button"
        variant="outline"
        aria-label={ariaLabel}
        aria-pressed={isProOnly}
        className={cn(
          "border-border/70 bg-background/80",
          isProOnly
            ? "border-[#3598db] bg-[#3598db] text-white hover:bg-[#2c84bf] hover:text-white dark:border-[#3598db] dark:bg-[#3598db] dark:text-white"
            : "border-[#f3c40f] bg-[#f3c40f] text-white hover:bg-[#d8ad0d] hover:text-white dark:border-[#f3c40f] dark:bg-[#f3c40f] dark:text-white",
        )}
        onClick={() => onCheckedChange(!isProOnly)}
      >
        {isProOnly ? "PRO" : "NUB"}
      </Button>
    )
  return (
    <Label
      htmlFor={id}
      className="flex h-9 w-fit items-center justify-start gap-2 rounded-lg border border-border/70 bg-background/80 px-3 text-[11px] font-medium tracking-[0.08em] text-foreground/80 uppercase"
    >
      <Switch
        id={id}
        checked={isProOnly}
        onCheckedChange={onCheckedChange}
        aria-label={ariaLabel}
        className="data-[state=unchecked]:bg-[#f3c40f] data-[state=unchecked]:shadow-[#f3c40f]/35 data-[state=checked]:bg-[#3598db] data-[state=checked]:shadow-[#3598db]/35 dark:data-[state=checked]:bg-[#3598db]"
      />
      <span>{isProOnly ? "PRO" : "NUB"}</span>
    </Label>
  )
}
