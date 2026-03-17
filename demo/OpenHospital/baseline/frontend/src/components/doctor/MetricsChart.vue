<template>
  <div class="metrics-chart-container">
    <div class="chart-header">
      <h3 class="chart-title">{{ title }}</h3>
      <div class="chart-legend">
        <span class="legend-item">
          <span class="legend-dot" :style="{ backgroundColor: lineColor }"></span>
          {{ metricName }}
        </span>
      </div>
    </div>

    <div class="chart-canvas" ref="chartCanvas">
      <svg :width="width" :height="height" class="pixel-chart">
        <g class="grid">
          <line
            v-for="i in 5"
            :key="`h-${i}`"
            :x1="padding.left"
            :y1="padding.top + (chartHeight / 4) * (i - 1)"
            :x2="width - padding.right"
            :y2="padding.top + (chartHeight / 4) * (i - 1)"
            class="grid-line"
          />
          <line
            v-for="i in 6"
            :key="`v-${i}`"
            :x1="padding.left + (chartWidth / 5) * (i - 1)"
            :y1="padding.top"
            :x2="padding.left + (chartWidth / 5) * (i - 1)"
            :y2="height - padding.bottom"
            class="grid-line"
          />
        </g>
        <g class="axes">
          <line
            :x1="padding.left"
            :y1="height - padding.bottom"
            :x2="width - padding.right"
            :y2="height - padding.bottom"
            class="axis-line"
          />
          <line
            :x1="padding.left"
            :y1="padding.top"
            :x2="padding.left"
            :y2="height - padding.bottom"
            class="axis-line"
          />
        </g>
        <g class="y-labels">
          <text
            v-for="i in 5"
            :key="`y-${i}`"
            :x="padding.left - 20"
            :y="padding.top + (chartHeight / 4) * (i - 1) + 4"
            class="axis-label"
            text-anchor="end"
          >
            {{ formatYValue(1 - (i - 1) * 0.25) }}
          </text>
        </g>
        <g class="x-labels">
          <template v-for="(point, i) in displayPoints" :key="`x-${i}`">
            <text
              v-if="i % Math.ceil(displayPoints.length / 5) === 0"
              :x="getX(point.patient_count)"
              :y="height - padding.bottom + 20"
              class="axis-label"
              text-anchor="middle"
            >
              {{ point.patient_count }}
            </text>
          </template>
        </g>
        <polyline
          v-if="displayPoints.length > 0"
          :points="linePoints"
          class="data-line"
          :style="{ stroke: lineColor }"
          fill="none"
        />
        <g class="data-points">
          <rect
            v-for="(point, i) in displayPoints"
            :key="`point-${i}`"
            :x="getX(point.patient_count) - 3"
            :y="getY(point[valueKey]) - 3"
            width="6"
            height="6"
            class="data-point"
            :style="{ fill: lineColor, stroke: '#fff' }"
            @mouseenter="showTooltip($event, point)"
            @mouseleave="hideTooltip"
          />
        </g>
        <text
          :x="width / 2"
          :y="height - 5"
          class="axis-title"
          text-anchor="middle"
        >
          PATIENTS
        </text>
        <text
          :x="15"
          :y="height / 2"
          class="axis-title"
          text-anchor="middle"
          :transform="`rotate(-90, 15, ${height / 2})`"
        >
          {{ yAxisLabel }}
        </text>
      </svg>
      <div
        v-if="tooltip.visible"
        class="chart-tooltip"
        :style="{
          left: tooltip.x + 'px',
          top: tooltip.y + 'px'
        }"
      >
        <div class="tooltip-content">
          <div class="tooltip-row">
            <span class="tooltip-label">PATIENTS:</span>
            <span class="tooltip-value">{{ tooltip.data.patient_count }}</span>
          </div>
          <div class="tooltip-row">
            <span class="tooltip-label">{{ metricName }}:</span>
            <span class="tooltip-value">{{ formatValue(tooltip.data[valueKey]) }}</span>
          </div>
          <div class="tooltip-row" v-if="tooltip.data.patient_id">
            <span class="tooltip-label">ID:</span>
            <span class="tooltip-value">{{ tooltip.data.patient_id }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface DataPoint {
  patient_count: number
  [key: string]: any
}

interface Props {
  title: string
  metricName: string
  yAxisLabel: string
  data: DataPoint[]
  valueKey: string
  lineColor?: string
  width?: number
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  lineColor: '#4ECDC4',
  width: 600,
  height: 300
})

const chartCanvas = ref<HTMLElement | null>(null)

const padding = {
  top: 20,
  right: 20,
  bottom: 55,
  left: 70
}

const chartWidth = computed(() => props.width - padding.left - padding.right)
const chartHeight = computed(() => props.height - padding.top - padding.bottom)

const displayPoints = computed(() => {
  return props.data.slice().sort((a, b) => a.patient_count - b.patient_count)
})

const maxPatientCount = computed(() => {
  if (displayPoints.value.length === 0) return 10
  return Math.max(...displayPoints.value.map(p => p.patient_count))
})

const getX = (patientCount: number) => {
  const ratio = patientCount / maxPatientCount.value
  return padding.left + ratio * chartWidth.value
}

const getY = (value: number) => {
  const ratio = 1 - value
  return padding.top + ratio * chartHeight.value
}

const linePoints = computed(() => {
  return displayPoints.value
    .map(point => `${getX(point.patient_count)},${getY(point[props.valueKey])}`)
    .join(' ')
})

const formatYValue = (value: number) => {
  return (value * 100).toFixed(0) + '%'
}

const formatValue = (value: number) => {
  return (value * 100).toFixed(1) + '%'
}
const tooltip = ref({
  visible: false,
  x: 0,
  y: 0,
  data: {} as DataPoint
})

const showTooltip = (event: MouseEvent, point: DataPoint) => {
  const rect = chartCanvas.value?.getBoundingClientRect()
  if (rect) {
    tooltip.value = {
      visible: true,
      x: event.clientX - rect.left + 10,
      y: event.clientY - rect.top - 10,
      data: point
    }
  }
}

const hideTooltip = () => {
  tooltip.value.visible = false
}
</script>

<style scoped>
.metrics-chart-container {
  background: white;
  padding: 0.625rem;
  font-family: 'Courier New', Courier, monospace;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  border-bottom: 0.125rem dashed #eee;
  padding-bottom: 0.5rem;
}

.chart-title {
  color: #333;
  font-size: 0.75rem;
  font-weight: 900;
  margin: 0;
  text-transform: uppercase;
}

.chart-legend {
  display: flex;
  gap: 1rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  color: #666;
  font-size: 0.625rem;
  font-weight: bold;
}

.legend-dot {
  width: 0.5rem;
  height: 0.5rem;
  border: 0.0625rem solid #333;
}

.chart-canvas {
  position: relative;
  background: #fff;
  border: 0.125rem solid #333;
  overflow: visible;
}

.pixel-chart {
  display: block;
  image-rendering: pixelated;
}

.grid-line {
  stroke: #eee;
  stroke-width: 1;
  stroke-dasharray: 2, 2;
}

.axis-line {
  stroke: #333;
  stroke-width: 2;
}

.axis-label {
  fill: #666;
  font-size: 0.5625rem;
  font-family: 'Courier New', Courier, monospace;
  font-weight: bold;
}

.axis-title {
  fill: #333;
  font-size: 0.625rem;
  font-weight: 900;
  font-family: 'Courier New', Courier, monospace;
}

.data-line {
  stroke-width: 2;
  stroke-linecap: square;
  stroke-linejoin: miter;
  fill: none;
}

.data-point {
  cursor: pointer;
  transition: width 0.1s, height 0.1s, x 0.1s, y 0.1s;
  stroke-width: 0.0625rem;
}

.data-point:hover {
  width: 0.5rem;
  height: 0.5rem;
  x: calc(var(--x) - 0.0625rem);
  stroke: #333 !important;
  stroke-width: 0.125rem;
}

.chart-tooltip {
  position: absolute;
  background: #fff;
  border: 0.125rem solid #333;
  padding: 0.375rem 0.625rem;
  pointer-events: none;
  z-index: 1000;
  box-shadow: 0.25rem 0.25rem 0 rgba(0,0,0,0.1);
  min-width: 7.5rem;
}

.tooltip-content {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.5625rem;
  font-family: 'Courier New', Courier, monospace;
}

.tooltip-label {
  color: #8b5a2b;
  font-weight: bold;
}

.tooltip-value {
  color: #333;
  font-weight: 900;
}
</style>
