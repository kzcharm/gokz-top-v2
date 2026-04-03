import { Link } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"

interface FeaturePlaceholderProps {
  section: string
  title: string
  description: string
  backTo?: string
  backLabel?: string
}

export function FeaturePlaceholder({
  section,
  title,
  description,
  backTo = "/",
  backLabel = "Back to home",
}: FeaturePlaceholderProps) {
  return (
    <div className="mx-auto max-w-5xl space-y-6 rounded-2xl border border-border/70 bg-card/60 p-6 shadow-sm backdrop-blur-sm sm:p-8">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-[0.16em] text-muted-foreground">
          {section}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="max-w-2xl text-sm text-muted-foreground sm:text-base">
          {description}
        </p>
      </div>

      <Button asChild variant="outline">
        <Link to={backTo}>{backLabel}</Link>
      </Button>
    </div>
  )
}
