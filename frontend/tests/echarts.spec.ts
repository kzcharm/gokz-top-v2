import { expect, test } from "@playwright/test"
import type { EChartsOption } from "echarts"
import { init, registerMap } from "../src/lib/echarts"

const options: Record<string, EChartsOption> = {
  bar: {
    grid: { containLabel: true },
    xAxis: { type: "category", data: ["A", "B"] },
    yAxis: {},
    series: [{ type: "bar", data: [1, 2] }],
    graphic: [{ type: "text", style: { text: "Chart annotation" } }],
  },
  line: {
    xAxis: { type: "category", data: ["A", "B"] },
    yAxis: {},
    tooltip: { trigger: "axis" },
    series: [
      { type: "line", data: [1, 2], labelLayout: { hideOverlap: true } },
    ],
  },
  pie: {
    legend: { type: "scroll" },
    series: [
      {
        type: "pie",
        data: [
          { name: "A", value: 1 },
          { name: "B", value: 2 },
        ],
      },
    ],
  },
  radar: {
    radar: {
      indicator: [
        { name: "A", max: 10 },
        { name: "B", max: 10 },
        { name: "C", max: 10 },
      ],
    },
    series: [{ type: "radar", data: [{ value: [1, 2, 3] }] }],
  },
  geo: {
    geo: { map: "registration-test" },
    series: [{ type: "scatter", coordinateSystem: "geo", data: [[0, 0, 1]] }],
  },
}

for (const [name, option] of Object.entries(options)) {
  test(`shared ECharts runtime renders ${name}`, () => {
    registerMap("registration-test", {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { name: "Test" },
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [-1, -1],
                [1, -1],
                [1, 1],
                [-1, 1],
                [-1, -1],
              ],
            ],
          },
        },
      ],
    })
    const chart = init(null, undefined, {
      renderer: "svg",
      ssr: true,
      width: 400,
      height: 300,
    })
    try {
      chart.setOption({ ...option, animation: false })
      const svg = chart.renderToSVGString()
      expect(svg).toContain("<path")
      if (name === "bar") expect(svg).toContain("Chart annotation")
      expect(chart.getOption().series).toHaveLength(1)
    } finally {
      chart.dispose()
    }
  })
}

test("shared ECharts runtime morphs between chart series", () => {
  const data = [
    { name: "A", value: 1 },
    { name: "B", value: 2 },
  ]
  const chart = init(null, undefined, {
    renderer: "svg",
    ssr: true,
    width: 400,
    height: 300,
  })
  try {
    chart.setOption({
      animationDuration: 0,
      animationDurationUpdate: 1000,
      xAxis: { type: "category", data: ["A", "B"] },
      yAxis: {},
      series: [{ id: "scores", type: "bar", data, universalTransition: true }],
    })
    chart.setOption({
      series: [{ id: "scores", type: "pie", data, universalTransition: true }],
    })
    expect(
      chart
        .getZr()
        .storage.getDisplayList(true)
        .some(
          (element) =>
            "__morphT" in element &&
            typeof element.__morphT === "number" &&
            element.__morphT >= 0,
        ),
    ).toBe(true)
  } finally {
    chart.dispose()
  }
})
