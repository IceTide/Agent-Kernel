<template>
  <div class="doctor-metrics-dashboard-container">
    <div class="doctor-metrics-dashboard">
      <div v-if="hasNoData" class="empty-state">
        <div class="empty-icon">📊</div>
        <div class="empty-title">NO METRICS DATA</div>
        <div class="empty-description">
          WAITING FOR DOCTOR ACTIVITY...
        </div>
      </div>

      <div v-else class="charts-grid">
        <div class="chart-wrapper">
          <MetricsChart
            title="DIAGNOSIS ACCURACY"
            metric-name="ACCURACY"
            y-axis-label="ACCURACY (%)"
            :data="metrics.diagnosis_history"
            value-key="accuracy"
            line-color="#ff6b6b"
            :width="chartWidth"
            :height="chartHeight"
          />
        </div>
        <div class="chart-wrapper">
          <MetricsChart
            title="EXAM PRECISION"
            metric-name="PRECISION"
            y-axis-label="PRECISION (%)"
            :data="metrics.examination_history"
            value-key="precision"
            line-color="#4ecdc4"
            :width="chartWidth"
            :height="chartHeight"
          />
        </div>
        <div class="chart-wrapper" v-if="metrics.treatment_history.length > 0">
          <MetricsChart
            title="TREATMENT SCORE"
            metric-name="SCORE"
            y-axis-label="SCORE (%)"
            :data="metrics.treatment_history"
            value-key="overall_score"
            line-color="#ffe66d"
            :width="chartWidth"
            :height="chartHeight"
          />
        </div>
        <div class="chart-wrapper empty-chart" v-else>
           <div class="empty-chart-content">
             <span class="pixel-icon">💊</span>
             <p>NO TREATMENT DATA</p>
             <small>WAITING FOR EVALUATION</small>
           </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import MetricsChart from './MetricsChart.vue'
import { getDoctorMetrics, getDoctorStats } from '@/api/doctor'

interface Props {
  doctorId?: string
}

const props = defineProps<Props>()
const route = useRoute()
const currentDoctorId = computed(() => {
  if (props.doctorId) return props.doctorId
  return route.params.id as string
})

interface DoctorMetrics {
  doctor_id: string
  diagnosis_total: number
  diagnosis_correct: number
  diagnosis_history: Array<{
    patient_count: number
    accuracy: number
    tick: number
    patient_id: string
    is_correct: boolean
  }>
  examination_total: number
  examination_precision_sum: number
  examination_history: Array<{
    patient_count: number
    precision: number
    tick: number
    patient_id: string
    current_precision: number
  }>
  treatment_total: number
  treatment_score_sum: number
  treatment_safety_sum: number
  treatment_effectiveness_sum: number
  treatment_personalization_sum: number
  treatment_history: Array<{
    patient_count: number
    overall_score: number
    safety: number
    effectiveness_alignment: number
    personalization: number
    tick: number
    patient_id: string
    current_score: number
  }>
}

interface DoctorStats {
  doctor_id: string
  diagnosis: {
    total: number
    correct: number
    accuracy: number
  }
  examination: {
    total: number
    average_precision: number
  }
  treatment: {
    total: number
    average_score: number
    average_safety: number
    average_effectiveness: number
    average_personalization: number
  }
}

const metrics = ref<DoctorMetrics>({
  doctor_id: '',
  diagnosis_total: 0,
  diagnosis_correct: 0,
  diagnosis_history: [],
  examination_total: 0,
  examination_precision_sum: 0,
  examination_history: [],
  treatment_total: 0,
  treatment_score_sum: 0,
  treatment_safety_sum: 0,
  treatment_effectiveness_sum: 0,
  treatment_personalization_sum: 0,
  treatment_history: []
})

const stats = ref<DoctorStats>({
  doctor_id: '',
  diagnosis: { total: 0, correct: 0, accuracy: 0 },
  examination: { total: 0, average_precision: 0 },
  treatment: {
    total: 0,
    average_score: 0,
    average_safety: 0,
    average_effectiveness: 0,
    average_personalization: 0
  }
})

const lastUpdateTime = ref('')
const chartWidth = ref(600)
const chartHeight = ref(300)

let refreshInterval: number | null = null

const hasNoData = computed(() => {
  const hasHistory = metrics.value.diagnosis_history.length > 0 ||
    metrics.value.examination_history.length > 0 ||
    metrics.value.treatment_history.length > 0
  const hasTotals = stats.value.diagnosis.total > 0 ||
    stats.value.examination.total > 0 ||
    stats.value.treatment.total > 0
    
  return !hasHistory && !hasTotals
})

const fetchMetrics = async () => {
  if (!currentDoctorId.value || currentDoctorId.value === 'undefined') {
    return
  }

  try {
    const [metricsData, statsData] = await Promise.all([
      getDoctorMetrics(currentDoctorId.value),
      getDoctorStats(currentDoctorId.value)
    ])

    metrics.value = metricsData
    stats.value = statsData
    lastUpdateTime.value = new Date().toLocaleTimeString('zh-CN')
  } catch (error) {
    console.error('Failed to fetch doctor metrics:', error)
  }
}

const updateChartSize = () => {
  const width = window.innerWidth
  if (width < 768) {
    chartWidth.value = 300
    chartHeight.value = 200
  } else if (width < 1200) {
    chartWidth.value = 380
    chartHeight.value = 220
  } else {
    chartWidth.value = 450
    chartHeight.value = 240
  }
}
watch(currentDoctorId, (newId) => {
  if (newId && newId !== 'undefined') {
    fetchMetrics()
  } else {
    metrics.value.diagnosis_history = []
    metrics.value.examination_history = []
    metrics.value.treatment_history = []
    stats.value.diagnosis.total = 0
    stats.value.examination.total = 0
    stats.value.treatment.total = 0
  }
})

onMounted(() => {
  fetchMetrics()
  updateChartSize()
  refreshInterval = window.setInterval(fetchMetrics, 3000)
  window.addEventListener('resize', updateChartSize)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
  window.removeEventListener('resize', updateChartSize)
})
</script>

<style scoped>
.doctor-metrics-dashboard-container {
  margin-bottom: 1.5rem;
}

.doctor-metrics-dashboard {
  background: #fff;
  border: 0.1875rem solid #333;
  padding: 1.5rem;
  box-shadow: 0.5rem 0.5rem 0 rgba(0,0,0,0.1);
  image-rendering: pixelated;
  font-family: 'Courier New', Courier, monospace;
  position: relative;
  overflow-x: auto;
  overflow-y: visible;
}

.doctor-metrics-dashboard::before {
  content: '';
  position: absolute;
  top: 0;
  left: 1.875rem;
  bottom: 0;
  width: 0.125rem;
  border-left: 0.0625rem solid #ffcccc;
  border-right: 0.0625rem solid #ffcccc;
  z-index: 1;
}



.charts-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.625rem;
  position: relative;
  z-index: 2;
  padding-left: 1.25rem;
  justify-items: center;
}

.chart-wrapper {
  min-height: 12.5rem;
  background: white;
  display: flex;
  justify-content: center;
  width: 100%;
}

.empty-state {
  background: #f8f9fa;
  border: 0.125rem dashed #ccc;
  padding: 2.5rem;
  text-align: center;
  margin: 0 0 0 1.25rem;
  position: relative;
  z-index: 2;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-title {
  font-size: 1rem;
  font-weight: 900;
  color: #333;
  margin-bottom: 0.5rem;
}

.empty-description {
  font-size: 0.75rem;
  color: #666;
  margin-bottom: 1rem;
  font-weight: bold;
}

.empty-stats {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
}

.empty-stat-item {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.empty-stat-label {
  font-size: 0.625rem;
  color: #8b5a2b;
  font-weight: bold;
}

.empty-stat-value {
  font-size: 0.75rem;
  color: #333;
  font-weight: bold;
}

.empty-chart {
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f9fa;
  border: 0.125rem dashed #ccc;
  min-height: 12.5rem;
  width: 100%;
}

.empty-chart-content {
  text-align: center;
  color: #999;
}

.empty-chart-content .pixel-icon {
  font-size: 1.5rem;
  margin-bottom: 0.5rem;
  display: block;
}

.empty-chart-content p {
  margin: 0;
  font-weight: 900;
  font-size: 0.625rem;
  color: #333;
}

.empty-chart-content small {
  font-size: 0.5rem;
}
@media (max-width: 75rem) {
  .charts-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 48rem) {
  .charts-grid {
    grid-template-columns: 1fr;
  }

  .doctor-metrics-dashboard {
    padding: 1rem;
  }

  .doctor-metrics-dashboard::before {
    left: 1rem;
  }

  .charts-grid, .empty-state {
    padding-left: 0.625rem;
    margin-left: 0.625rem;
  }
}
</style>
