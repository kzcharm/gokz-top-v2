import type { CSSProperties } from "react"

import type {
  JumpstatVisualizationPublic,
  JumpstatVisualizationSample,
  JumpstatVisualizationStrafeType,
} from "@/client"
import { cn } from "@/lib/utils"

const STRAFE_TYPE_COLORS: Record<JumpstatVisualizationStrafeType, string> = {
  OVERLAP: "#d946ef",
  NONE: "#94a3b8",
  LEFT: "#0f172a",
  OVERLAP_LEFT: "#0891b2",
  NONE_LEFT: "#16a34a",
  RIGHT: "#2563eb",
  OVERLAP_RIGHT: "#06b6d4",
  NONE_RIGHT: "#22c55e",
}

function getRoutePoint(
  sample: JumpstatVisualizationSample,
  visualization: JumpstatVisualizationPublic,
) {
  const width = 100
  const height = 120
  const padding = 10
  const drawableWidth = width - padding * 2
  const drawableHeight = height - padding * 2
  const xRange = Math.max(
    visualization.bounds.max_x - visualization.bounds.min_x,
    1,
  )
  const yRange = Math.max(
    visualization.bounds.max_y - visualization.bounds.min_y,
    1,
  )

  return {
    x:
      padding +
      ((sample.x - visualization.bounds.min_x) / xRange) * drawableWidth,
    y:
      height -
      padding -
      ((sample.y - visualization.bounds.min_y) / yRange) * drawableHeight,
  }
}

function Strip({
  label,
  samples,
  getActive,
  getStyle,
}: {
  label: string
  samples: JumpstatVisualizationSample[]
  getActive: (sample: JumpstatVisualizationSample) => boolean
  getStyle: (sample: JumpstatVisualizationSample) => CSSProperties
}) {
  return (
    <div className="grid grid-cols-[2rem_1fr] items-center gap-3">
      <div className="text-xs font-semibold tracking-[0.18em] text-muted-foreground uppercase">
        {label}
      </div>
      <div className="overflow-x-auto">
        <div
          className="grid gap-1"
          style={{
            gridTemplateColumns: `repeat(${Math.max(samples.length, 1)}, minmax(0, 1fr))`,
          }}
        >
          {samples.map((sample) => (
            <div
              key={`${label}-${sample.index}`}
              className={cn(
                "h-5 min-w-3 rounded-sm border border-border/50",
                getActive(sample) ? "" : "bg-background/70",
              )}
              style={getActive(sample) ? getStyle(sample) : undefined}
              title={`${label} ${sample.index + 1}`}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

export function JumpstatRouteVisualization({
  visualization,
  title,
  deviationLabel,
  aLabel,
  dLabel,
  mouseLabel,
}: {
  visualization: JumpstatVisualizationPublic
  title: string
  deviationLabel: string
  aLabel: string
  dLabel: string
  mouseLabel: string
}) {
  const points = visualization.samples.map((sample) => ({
    sample,
    ...getRoutePoint(sample, visualization),
  }))

  return (
    <div className="rounded-[26px] border border-border/70 bg-background/70 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-semibold tracking-[0.14em] text-foreground uppercase">
          {title}
        </div>
        <div className="text-sm text-muted-foreground">
          {deviationLabel}:{" "}
          <span className="font-mono font-semibold tabular-nums text-foreground">
            {visualization.deviation_angle.toFixed(2)}°
          </span>
        </div>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-border/60 bg-card">
        <svg
          viewBox="0 0 100 120"
          className="h-[20rem] w-full bg-[radial-gradient(circle_at_top,_rgba(148,163,184,0.15),_transparent_55%)]"
          role="img"
          aria-label={title}
        >
          <title>{title}</title>
          <defs>
            <pattern
              id="jumpstat-grid"
              width="10"
              height="10"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 10 0 L 0 0 0 10"
                fill="none"
                stroke="rgba(148,163,184,0.15)"
                strokeWidth="0.5"
              />
            </pattern>
          </defs>
          <rect width="100" height="120" fill="url(#jumpstat-grid)" />
          <line
            x1="50"
            y1="8"
            x2="50"
            y2="112"
            stroke="rgba(148,163,184,0.2)"
            strokeDasharray="2 3"
          />
          {points.slice(1).map((point, index) => {
            const previous = points[index]
            return (
              <line
                key={`segment-${point.sample.index}`}
                x1={previous.x}
                y1={previous.y}
                x2={point.x}
                y2={point.y}
                stroke={STRAFE_TYPE_COLORS[point.sample.strafe_type]}
                strokeWidth="2.8"
                strokeLinecap="round"
              />
            )
          })}
          {points.map((point) => (
            <circle
              key={`point-${point.sample.index}`}
              cx={point.x}
              cy={point.y}
              r="2.2"
              fill={STRAFE_TYPE_COLORS[point.sample.strafe_type]}
              stroke="rgba(255,255,255,0.7)"
              strokeWidth="0.7"
            />
          ))}
        </svg>
      </div>

      <div className="mt-4 space-y-2">
        <Strip
          label={aLabel}
          samples={visualization.samples}
          getActive={(sample) => sample.a_pressed}
          getStyle={(sample) => ({
            backgroundColor: STRAFE_TYPE_COLORS[sample.strafe_type],
          })}
        />
        <Strip
          label={dLabel}
          samples={visualization.samples}
          getActive={(sample) => sample.d_pressed}
          getStyle={(sample) => ({
            backgroundColor: STRAFE_TYPE_COLORS[sample.strafe_type],
          })}
        />
        <Strip
          label={mouseLabel}
          samples={visualization.samples}
          getActive={(sample) => sample.mouse_direction !== "NONE"}
          getStyle={(sample) => ({
            backgroundColor:
              sample.mouse_direction === "LEFT"
                ? "#0f172a"
                : sample.mouse_direction === "RIGHT"
                  ? "#2563eb"
                  : "#cbd5e1",
          })}
        />
      </div>
    </div>
  )
}
