import {
  BarChart,
  LineChart,
  PieChart,
  RadarChart,
  ScatterChart,
} from "echarts/charts"
import {
  GeoComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  RadarComponent,
  TooltipComponent,
} from "echarts/components"
import { use } from "echarts/core"
import {
  LabelLayout,
  LegacyGridContainLabel,
  UniversalTransition,
} from "echarts/features"
import { CanvasRenderer, SVGRenderer } from "echarts/renderers"

use([
  BarChart,
  LineChart,
  PieChart,
  RadarChart,
  ScatterChart,
  GeoComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  RadarComponent,
  TooltipComponent,
  LabelLayout,
  LegacyGridContainLabel,
  UniversalTransition,
  CanvasRenderer,
  SVGRenderer,
])

export type { EChartsOption } from "echarts"
export type { EChartsType } from "echarts/core"
export { init, registerMap } from "echarts/core"
