import type {
  JumpstatVisualizationPublic,
  JumpstatVisualizationSample,
} from "@/client"

const DISTBUG_BEAM_COLORS = {
  neutral: "#FFBF00",
  loss: "#FF00FF",
  gain: "#85eb34",
  duck: "#001F7F",
} as const

const DISTBUG_STRAFE_COLORS = {
  overlap: "#FF00FF",
  none: "#2A2A2A",
  turn: "#FFFFFF",
  overlapTurn: "#00BFBF",
  noKeyTurn: "#408040",
} as const

const DISTBUG_MOUSE_COLORS = {
  left: "#FFBF00",
  none: "#2A2A2A",
  right: "#003FFF",
} as const

function getBeamColor(sample: JumpstatVisualizationSample) {
  switch (sample.strafe_type) {
    case "OVERLAP":
    case "OVERLAP_LEFT":
    case "OVERLAP_RIGHT":
      return DISTBUG_BEAM_COLORS.loss
    case "LEFT":
    case "RIGHT":
      return DISTBUG_BEAM_COLORS.gain
    case "NONE":
    case "NONE_LEFT":
    case "NONE_RIGHT":
      return DISTBUG_BEAM_COLORS.neutral
  }
}

function getRouteCoordinates(
  x: number,
  y: number,
  visualization: JumpstatVisualizationPublic,
) {
  const width = 100
  const height = 120
  const padding = 10
  const drawableHalfWidth = (width - padding * 2) / 2
  const drawableHeight = height - padding * 2
  const maxAbsX = Math.max(
    Math.abs(visualization.bounds.min_x),
    Math.abs(visualization.bounds.max_x),
    1,
  )
  const maxY = Math.max(visualization.bounds.max_y, 1)
  const scale = Math.min(drawableHalfWidth / maxAbsX, drawableHeight / maxY)

  return {
    x: width / 2 + x * scale,
    y: height - padding - y * scale,
  }
}

function getRoutePoint(
  sample: JumpstatVisualizationSample,
  visualization: JumpstatVisualizationPublic,
) {
  return getRouteCoordinates(sample.x, sample.y, visualization)
}

function getStrafeLedColor(
  sample: JumpstatVisualizationSample,
  side: "left" | "right",
) {
  if (side === "left") {
    switch (sample.strafe_type) {
      case "OVERLAP":
        return DISTBUG_STRAFE_COLORS.overlap
      case "NONE":
      case "RIGHT":
      case "NONE_RIGHT":
      case "OVERLAP_RIGHT":
        return DISTBUG_STRAFE_COLORS.none
      case "LEFT":
        return DISTBUG_STRAFE_COLORS.turn
      case "OVERLAP_LEFT":
        return DISTBUG_STRAFE_COLORS.overlapTurn
      case "NONE_LEFT":
        return DISTBUG_STRAFE_COLORS.noKeyTurn
    }
  }

  switch (sample.strafe_type) {
    case "OVERLAP":
      return DISTBUG_STRAFE_COLORS.overlap
    case "NONE":
    case "LEFT":
    case "NONE_LEFT":
    case "OVERLAP_LEFT":
      return DISTBUG_STRAFE_COLORS.none
    case "RIGHT":
      return DISTBUG_STRAFE_COLORS.turn
    case "OVERLAP_RIGHT":
      return DISTBUG_STRAFE_COLORS.overlapTurn
    case "NONE_RIGHT":
      return DISTBUG_STRAFE_COLORS.noKeyTurn
  }
}

function getMouseLedColor(sample: JumpstatVisualizationSample) {
  switch (sample.mouse_direction) {
    case "LEFT":
      return DISTBUG_MOUSE_COLORS.left
    case "NONE":
      return DISTBUG_MOUSE_COLORS.none
    case "RIGHT":
      return DISTBUG_MOUSE_COLORS.right
  }
}

function LedStrip({
  label,
  samples,
  getColor,
}: {
  label: string
  samples: JumpstatVisualizationSample[]
  getColor: (sample: JumpstatVisualizationSample) => string
}) {
  return (
    <div className="flex items-center gap-[10px] font-mono">
      <div className="w-5 shrink-0 text-right text-xs font-medium text-muted-foreground">
        {label}
      </div>
      <div className="flex flex-1 justify-center overflow-x-auto">
        <div className="flex items-center gap-[2px]">
          {samples.map((sample) => (
            <div
              key={`${label}-${sample.index}`}
              className="h-[22px] w-[5px] shrink-0 rounded-[2px] border border-white/10 transition-opacity hover:opacity-70"
              style={{ backgroundColor: getColor(sample) }}
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
  legendLabel,
  neutralLabel,
  gainLabel,
  lossLabel,
  duckLabel,
  aLabel,
  dLabel,
  mouseLabel,
}: {
  visualization: JumpstatVisualizationPublic
  title: string
  deviationLabel: string
  legendLabel: string
  neutralLabel: string
  gainLabel: string
  lossLabel: string
  duckLabel: string
  aLabel: string
  dLabel: string
  mouseLabel: string
}) {
  const points = visualization.samples.map((sample) => ({
    sample,
    ...getRoutePoint(sample, visualization),
  }))
  const originPoint = getRouteCoordinates(0, 0, visualization)

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
        <div className="border-b border-border/60 px-4 py-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
            <span className="font-semibold tracking-[0.14em] uppercase">
              {legendLabel}
            </span>
            {[
              { color: DISTBUG_BEAM_COLORS.neutral, label: neutralLabel },
              { color: DISTBUG_BEAM_COLORS.gain, label: gainLabel },
              { color: DISTBUG_BEAM_COLORS.loss, label: lossLabel },
              { color: DISTBUG_BEAM_COLORS.duck, label: duckLabel },
            ].map((item) => (
              <div
                key={item.label}
                className="flex items-center gap-2 whitespace-nowrap"
              >
                <span
                  className="h-0.5 w-6 rounded-full"
                  style={{ backgroundColor: item.color }}
                  aria-hidden="true"
                />
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        </div>
        <svg
          viewBox="0 0 100 120"
          className="h-[36rem] w-full bg-[radial-gradient(circle_at_top,_rgba(148,163,184,0.15),_transparent_55%)]"
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
          {points[0] ? (
            <line
              x1={originPoint.x}
              y1={originPoint.y}
              x2={points[0].x}
              y2={points[0].y}
              stroke={getBeamColor(points[0].sample)}
              strokeWidth="1.9"
              strokeLinecap="round"
            />
          ) : null}
          {points.slice(1).map((point, index) => {
            const previous = points[index]
            return (
              <line
                key={`segment-${point.sample.index}`}
                x1={previous.x}
                y1={previous.y}
                x2={point.x}
                y2={point.y}
                stroke={getBeamColor(point.sample)}
                strokeWidth="1.9"
                strokeLinecap="round"
              />
            )
          })}
          <circle
            cx={originPoint.x}
            cy={originPoint.y}
            r="1.4"
            fill="#f8fafc"
            stroke="rgba(15,23,42,0.65)"
            strokeWidth="0.55"
          />
        </svg>
      </div>

      <div className="mt-4 space-y-3">
        <LedStrip
          label={aLabel}
          samples={visualization.samples}
          getColor={(sample) => getStrafeLedColor(sample, "left")}
        />
        <LedStrip
          label={dLabel}
          samples={visualization.samples}
          getColor={(sample) => getStrafeLedColor(sample, "right")}
        />
        <LedStrip
          label={mouseLabel}
          samples={visualization.samples}
          getColor={getMouseLedColor}
        />
      </div>
    </div>
  )
}
