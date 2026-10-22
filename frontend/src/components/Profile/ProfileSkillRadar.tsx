import { useTranslation } from "react-i18next"
import {
  formatRating,
  type ProfileSkillKey,
  type ProfileSkillRatings,
} from "./profile-utils"

const SKILL_KEYS: ProfileSkillKey[] = [
  "boxtech",
  "strafe",
  "bhop",
  "climb",
  "ladder",
  "slide",
]

type SkillRadarScale = "global" | "relative"

const RELATIVE_RADAR_BASE_INNER_RATIO = 0.25
const RELATIVE_RADAR_ABSOLUTE_STRENGTH_WEIGHT = 0.55

function getSkillRadarPlotValues(
  values: Array<number | null>,
  scale: SkillRadarScale,
) {
  const globalValues = values.map((value) =>
    value === null ? 0 : Math.min(1, Math.max(0, value / 11)),
  )

  // Keep the global scale implementation archived here so it can be restored
  // without rebuilding its plotting behavior. The profile currently renders
  // the relative scale directly.
  if (scale === "global") {
    return globalValues
  }

  const availableValues = globalValues.filter(
    (_, index) => values[index] !== null,
  )
  if (availableValues.length === 0) {
    return values.map(() => 0)
  }

  const minimum = Math.min(...availableValues)
  const maximum = Math.max(...availableValues)
  const range = maximum - minimum
  if (range < 0.005) {
    return globalValues
  }

  const innerRatio =
    RELATIVE_RADAR_BASE_INNER_RATIO +
    RELATIVE_RADAR_ABSOLUTE_STRENGTH_WEIGHT * minimum

  return globalValues.map((value, index) => {
    if (values[index] === null) {
      return 0
    }
    const position = (value - minimum) / range
    return maximum * (innerRatio + position * (1 - innerRatio))
  })
}

export function SkillRadar({
  ratings,
  card = false,
}: {
  ratings: ProfileSkillRatings | null
  card?: boolean
}) {
  const { t } = useTranslation()
  const size = card ? 400 : 220
  const center = size / 2
  const radius = card ? 116 : 74
  const labels = SKILL_KEYS.map((skill) => ({
    value: ratings?.[skill]?.rating ?? null,
    label: t(
      `profile.skillRadar.${skill}` as
        | "profile.skillRadar.boxtech"
        | "profile.skillRadar.strafe"
        | "profile.skillRadar.bhop"
        | "profile.skillRadar.climb"
        | "profile.skillRadar.ladder"
        | "profile.skillRadar.slide",
    ),
  }))
  const plotValues = getSkillRadarPlotValues(
    labels.map((skill) => skill.value),
    "relative",
  )

  const polygon = labels
    .map((_, index) => {
      const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2
      const pointRadius = plotValues[index] * radius
      const x = center + Math.cos(angle) * pointRadius
      const y = center + Math.sin(angle) * pointRadius
      return `${x},${y}`
    })
    .join(" ")

  return (
    <div className="w-full">
      <div className="flex w-full justify-center">
        <svg
          viewBox={`0 0 ${size} ${size}`}
          className={
            card
              ? "aspect-square w-full max-w-[320px]"
              : "h-[220px] w-[220px] overflow-visible"
          }
          role="img"
          aria-label={t("profile.skillRadar.relativeAriaLabel")}
        >
          {[0.25, 0.5, 0.75, 1].map((step) => (
            <polygon
              key={step}
              data-testid="profile-skill-radar-grid-line"
              points={labels
                .map((_, index) => {
                  const angle =
                    (Math.PI * 2 * index) / labels.length - Math.PI / 2
                  const x = center + Math.cos(angle) * radius * step
                  const y = center + Math.sin(angle) * radius * step
                  return `${x},${y}`
                })
                .join(" ")}
              fill="none"
              stroke="currentColor"
              className="text-border/65"
              strokeWidth="1"
            />
          ))}
          {labels.map((_, index) => {
            const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2
            const x = center + Math.cos(angle) * radius
            const y = center + Math.sin(angle) * radius
            return (
              <line
                key={index}
                x1={center}
                y1={center}
                x2={x}
                y2={y}
                stroke="currentColor"
                className="text-border/65"
                strokeWidth="1"
              />
            )
          })}
          {labels.every((skill) => skill.value !== null) && (
            <polygon
              data-testid="profile-skill-radar-polygon"
              points={polygon}
              fill="rgba(127,119,221,0.18)"
              stroke="rgba(127,119,221,1)"
              strokeWidth="2"
            />
          )}
          {labels.map((skill, index) => {
            const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2
            const pointRadius = plotValues[index] * radius
            const x = center + Math.cos(angle) * pointRadius
            const y = center + Math.sin(angle) * pointRadius
            const labelRadius = radius + (card ? 52 : 26)
            const lx = center + Math.cos(angle) * labelRadius
            const ly = center + Math.sin(angle) * labelRadius
            return (
              <g key={skill.label}>
                {skill.value !== null && (
                  <circle cx={x} cy={y} r="4" fill="rgba(127,119,221,1)" />
                )}
                <text
                  x={lx}
                  y={ly}
                  data-skill-label={SKILL_KEYS[index]}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className={
                    card
                      ? "fill-muted-foreground text-[24px] font-medium"
                      : "fill-muted-foreground text-[10px] font-medium"
                  }
                >
                  {card ? (
                    <>
                      <tspan x={lx} dy="-0.4em" fontSize="20">
                        {skill.label}
                      </tspan>
                      <tspan x={lx} dy="1.2em" fontSize="28">
                        {skill.value === null ? "—" : formatRating(skill.value)}
                      </tspan>
                    </>
                  ) : (
                    `${skill.label} ${skill.value === null ? "—" : formatRating(skill.value)}`
                  )}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
