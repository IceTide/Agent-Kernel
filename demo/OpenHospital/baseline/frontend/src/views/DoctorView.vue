<script setup lang="ts">
import { onMounted, computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { PatientEvaluationCard } from '@/components/doctor'
import DoctorMetricsDashboard from '@/components/doctor/DoctorMetricsDashboard.vue'
import { useDoctorStore } from '@/stores'
import { ArrowLeft, OfficeBuilding, Location, User, ArrowRight, Loading, CircleClose, Warning } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const doctorStore = useDoctorStore()

const doctorId = computed(() => route.params.id as string)
const CURRENT_PATIENTS_BATCH_SIZE = 12
const TREATMENT_DETAILS_BATCH_SIZE = 8

const visibleCurrentPatientsCount = ref(CURRENT_PATIENTS_BATCH_SIZE)
const visibleTreatmentDetailsCount = ref(TREATMENT_DETAILS_BATCH_SIZE)

const visibleCurrentPatients = computed(() => {
  return doctorStore.currentDoctor?.current_patients?.slice(0, visibleCurrentPatientsCount.value) || []
})

const visiblePatientEvaluations = computed(() => {
  return doctorStore.evaluation?.patients?.slice(0, visibleTreatmentDetailsCount.value) || []
})

const hasMoreCurrentPatients = computed(() => {
  const total = doctorStore.currentDoctor?.current_patients?.length || 0
  return visibleCurrentPatientsCount.value < total
})

const hasMorePatientEvaluations = computed(() => {
  const total = doctorStore.evaluation?.patients?.length || 0
  return visibleTreatmentDetailsCount.value < total
})

onMounted(async () => {
  if (doctorId.value) {
    doctorStore.selectedDoctorId = doctorId.value
    await Promise.all([
      doctorStore.fetchDoctorDetail(doctorId.value),
      doctorStore.fetchEvaluation(doctorId.value),
      doctorStore.fetchDoctorConsultations(doctorId.value),
    ])
  }
})

function goBack() {
  router.push('/')
}

async function retryLoad() {
  if (doctorId.value) {
    doctorStore.selectedDoctorId = doctorId.value
    await Promise.all([
      doctorStore.fetchDoctorDetail(doctorId.value),
      doctorStore.fetchEvaluation(doctorId.value),
      doctorStore.fetchDoctorConsultations(doctorId.value),
    ])
  }
}

function loadMoreCurrentPatients() {
  const total = doctorStore.currentDoctor?.current_patients?.length || 0
  visibleCurrentPatientsCount.value = Math.min(
    total,
    visibleCurrentPatientsCount.value + CURRENT_PATIENTS_BATCH_SIZE
  )
}

function loadMorePatientEvaluations() {
  const total = doctorStore.evaluation?.patients?.length || 0
  visibleTreatmentDetailsCount.value = Math.min(
    total,
    visibleTreatmentDetailsCount.value + TREATMENT_DETAILS_BATCH_SIZE
  )
}

const formatPercentage = (value: number) => {
  return (value * 100).toFixed(1) + '%'
}

const selectedConsultationPatientId = ref<string | null>(null)

const consultationGroups = computed(() => doctorStore.consultationGroups)
const selectedConsultationGroup = computed(() => {
  if (!consultationGroups.value.length) return null
  if (!selectedConsultationPatientId.value) {
    return consultationGroups.value[0]
  }
  return consultationGroups.value.find(
    group => group.patient_id === selectedConsultationPatientId.value
  ) || consultationGroups.value[0]
})

function getDoctorAvatar(doctorId: string) {
  let hash = 0
  for (let i = 0; i < doctorId.length; i += 1) {
    hash = (hash * 31 + doctorId.charCodeAt(i)) % 1000
  }
  return hash % 2 === 0 ? '/doctor_male.png' : '/doctor_female.png'
}

watch(consultationGroups, (groups) => {
  if (!groups.length) {
    selectedConsultationPatientId.value = null
    return
  }
  if (!selectedConsultationPatientId.value) {
    selectedConsultationPatientId.value = groups[0].patient_id
  }
}, { immediate: true })

watch(doctorId, () => {
  visibleCurrentPatientsCount.value = CURRENT_PATIENTS_BATCH_SIZE
  visibleTreatmentDetailsCount.value = TREATMENT_DETAILS_BATCH_SIZE
}, { immediate: true })

function selectConsultationPatient(patientId: string) {
  selectedConsultationPatientId.value = patientId
}

function formatTick(value?: number) {
  if (value == null) return '-'
  return `T${value}`
}

function formatDoctorLabel(doctor: string) {
  return `Dr. ${doctor.replace(/^Doctor_/, '')}`
}
</script>

<template>
  <MainLayout>
    <div class="doctor-view">
      <div class="view-header">
        <el-button :icon="ArrowLeft" @click="goBack">Back</el-button>
        <h1 v-if="doctorStore.currentDoctor">
          {{ doctorStore.currentDoctor.name }} - Doctor Details
        </h1>
      </div>
      
      <el-scrollbar v-if="doctorStore.currentDoctor" class="view-content">
        <div class="content-wrapper">
          <section class="section">
            <h2>Doctor Profile</h2>
            <div class="doctor-profile-card">
              <div class="avatar">
                <img :src="getDoctorAvatar(doctorStore.currentDoctor.id)" alt="Doctor" class="avatar-image" />
              </div>
              <div class="info">
                <h3>{{ doctorStore.currentDoctor.name }}</h3>
                <p class="doctor-id">{{ doctorStore.currentDoctor.id }}</p>
                <p class="department">
                  <el-icon><OfficeBuilding /></el-icon>
                  {{ doctorStore.currentDoctor.department }}
                </p>
                <p class="location">
                  <el-icon><Location /></el-icon>
                  {{ doctorStore.currentDoctor.consultation_room }}
                </p>
              </div>
              <div class="specialties">
                <h4>Specialties</h4>
                <div class="specialty-tags">
                  <el-tag 
                    v-for="specialty in doctorStore.currentDoctor.specialties"
                    :key="specialty"
                    type="primary"
                  >
                    {{ specialty }}
                  </el-tag>
                </div>
              </div>
            </div>
          </section>
          <section v-if="doctorStore.currentDoctor.current_patients?.length" class="section">
            <h2>Current Patients ({{ doctorStore.currentDoctor.current_patients.length }})</h2>
            <div class="patients-grid">
              <div
                v-for="patient in visibleCurrentPatients"
                :key="patient.id"
                class="patient-mini-card"
                @click="router.push(`/patient/${patient.id}`)"
              >
                <el-icon><User /></el-icon>
                <span>{{ patient.id }}</span>
                <el-icon class="arrow"><ArrowRight /></el-icon>
              </div>
            </div>
            <div v-if="hasMoreCurrentPatients" class="load-more-wrapper">
              <el-button plain @click="loadMoreCurrentPatients">
                Load More ({{ visibleCurrentPatients.length }}/{{ doctorStore.currentDoctor.current_patients.length }})
              </el-button>
            </div>
          </section>
          <section class="section">
            <h2>Doctor Consultations by Patient</h2>
            <div v-if="doctorStore.consultationsLoading" class="loading-placeholder">
              <el-icon class="is-loading" :size="32"><Loading /></el-icon>
              <span>Loading consultation messages...</span>
            </div>
            <div v-else-if="doctorStore.consultationsError" class="consultation-error">
              <span>{{ doctorStore.consultationsError }}</span>
            </div>
            <div v-else-if="consultationGroups.length === 0" class="consultation-empty">
              <span>No doctor-to-doctor consultations yet.</span>
            </div>
            <div v-else class="consultations-layout">
              <div class="consultation-patients">
                <div
                  v-for="group in consultationGroups"
                  :key="group.patient_id"
                  class="consultation-patient-card"
                  :class="{ active: group.patient_id === selectedConsultationGroup?.patient_id }"
                  @click="selectConsultationPatient(group.patient_id)"
                >
                  <div class="patient-id">{{ group.patient_id }}</div>
                  <div class="patient-meta">
                    <span>{{ group.message_count }} msgs</span>
                    <span>Last: {{ formatTick(group.last_message_tick) }}</span>
                  </div>
                </div>
              </div>
              <div class="consultation-thread" v-if="selectedConsultationGroup">
                <div class="consultation-thread-header">
                  <span>Patient: {{ selectedConsultationGroup.patient_id }}</span>
                  <span>{{ selectedConsultationGroup.message_count }} messages</span>
                </div>
                <div class="consultation-thread-body">
                  <div
                    v-for="message in selectedConsultationGroup.messages"
                    :key="message.id"
                    class="consultation-message"
                  >
                    <div class="message-meta">
                      <span class="message-tick">{{ formatTick(message.created_at) }}</span>
                      <span class="message-sender">{{ formatDoctorLabel(message.sender) }}</span>
                      <span class="message-arrow">-&gt;</span>
                      <span class="message-receiver">{{ formatDoctorLabel(message.receiver) }}</span>
                    </div>
                    <div class="message-content">{{ message.content }}</div>
                  </div>
                </div>
              </div>
            </div>
          </section>
          <section class="section">
            <DoctorMetricsDashboard />
          </section>
          <section v-if="doctorStore.evaluation" class="section">
            <h2>Treatment Evaluation</h2>
            <div class="stats-grid">
              <div class="stat-card">
                <div class="stat-value">{{ doctorStore.evaluation.summary.total_patients }}</div>
                <div class="stat-label">Total Patients</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">
                  {{ doctorStore.evaluation.summary.correct_diagnoses }} / {{ doctorStore.evaluation.summary.total_diagnoses }}
                </div>
                <div class="stat-label">Correct / Total Diagnoses</div>
              </div>
              <div class="stat-card">
                <div class="stat-value" :style="{ 
                  color: doctorStore.evaluation.summary.diagnosis_accuracy >= 0.8 ? 'var(--success-color)' : 
                         doctorStore.evaluation.summary.diagnosis_accuracy >= 0.5 ? 'var(--warning-color)' : 'var(--danger-color)' 
                }">
                  {{ doctorStore.evaluation.summary.diagnosis_accuracy != null ? formatPercentage(doctorStore.evaluation.summary.diagnosis_accuracy) : 'N/A' }}
                </div>
                <div class="stat-label">Diagnosis Accuracy</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ doctorStore.evaluation.summary.total_examinations }}</div>
                <div class="stat-label">Total Examinations</div>
              </div>
              <div class="stat-card">
                <div class="stat-value" :style="{ 
                  color: doctorStore.evaluation.summary.average_examination_precision >= 0.8 ? 'var(--success-color)' : 
                         doctorStore.evaluation.summary.average_examination_precision >= 0.5 ? 'var(--warning-color)' : 'var(--danger-color)' 
                }">
                  {{ doctorStore.evaluation.summary.average_examination_precision != null ? formatPercentage(doctorStore.evaluation.summary.average_examination_precision) : 'N/A' }}
                </div>
                <div class="stat-label">Examination Precision</div>
              </div>
              <div class="stat-card">
                <el-tag v-if="doctorStore.evaluation.summary.has_ground_truth" type="success">
                  Has Ground Truth
                </el-tag>
                <el-tag v-else type="info">
                  No Ground Truth
                </el-tag>
                <div class="stat-label">Data Source</div>
              </div>
            </div>
            <div class="patients-evaluation">
              <h3>Patient Treatment Details ({{ doctorStore.evaluation.patients.length }})</h3>
              <div class="evaluation-cards">
                <PatientEvaluationCard 
                  v-for="patientEval in visiblePatientEvaluations"
                  :key="patientEval.patient_id"
                  :evaluation="patientEval"
                />
              </div>
              <div v-if="hasMorePatientEvaluations" class="load-more-wrapper">
                <el-button plain @click="loadMorePatientEvaluations">
                  Load More ({{ visiblePatientEvaluations.length }}/{{ doctorStore.evaluation.patients.length }})
                </el-button>
              </div>
            </div>
          </section>
          <section v-else-if="doctorStore.evaluationLoading" class="section">
            <div class="loading-placeholder">
              <el-icon class="is-loading" :size="32"><Loading /></el-icon>
              <span>Loading evaluation data...</span>
            </div>
          </section>
          <section v-else class="section">
            <el-alert
              title="No Evaluation Data"
              type="info"
              description="This doctor has not treated any patients yet, or the ground truth data file does not exist"
              :closable="false"
            />
          </section>
        </div>
      </el-scrollbar>
      <div v-else-if="doctorStore.error" class="error-state">
        <el-icon :size="48" color="#f56c6c"><CircleClose /></el-icon>
        <h3>Loading Failed</h3>
        <p>{{ doctorStore.error }}</p>
        <el-button type="primary" @click="retryLoad">Retry</el-button>
        <el-button @click="goBack">Back Home</el-button>
      </div>
      <div v-else-if="doctorStore.loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>Loading...</span>
      </div>
      <div v-else class="empty-state">
        <el-icon :size="48"><Warning /></el-icon>
        <h3>Doctor data not found</h3>
        <el-button @click="goBack">Back Home</el-button>
      </div>
    </div>
  </MainLayout>
</template>

<style scoped lang="scss">
.doctor-view {
  height: 100%;
  display: flex;
  flex-direction: column;

  .view-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.5rem;
    background: white;
    border-bottom: 0.0625rem solid var(--border-color-lighter);

    h1 {
      margin: 0;
      font-size: 1.25rem;
    }
  }

  .view-content {
    flex: 1;

    .content-wrapper {
      max-width: 75rem;
      margin: 0 auto;
      padding: 1.5rem;
    }

    .section {
      margin-bottom: 2rem;

      h2 {
        margin: 0 0 1rem 0;
        font-size: var(--font-size-lg);
        font-weight: 400;
        color: var(--text-primary);
      }
    }

    .doctor-profile-card {
      display: flex;
      gap: 1.5rem;
      padding: 1.5rem;
      background: white;
      border-radius: 0.75rem;

      .avatar {
        width: 6.25rem;
        height: 6.25rem;
        background: transparent;
        border-radius: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;

        .avatar-image {
          width: 100%;
          height: 100%;
          object-fit: contain;
          image-rendering: -moz-crisp-edges;
          image-rendering: -webkit-crisp-edges;
          image-rendering: pixelated;
          image-rendering: crisp-edges;
          -ms-interpolation-mode: nearest-neighbor;
        }
      }

      .info {
        flex: 1;

        h3 {
          margin: 0 0 0.5rem 0;
          font-size: 1.5rem;
        }

        .doctor-id {
          margin: 0 0 0.75rem 0;
          color: var(--text-secondary);
          font-size: 0.8125rem;
        }

        .department, .location {
          display: flex;
          align-items: center;
          gap: 0.375rem;
          margin: 0 0 0.5rem 0;
          font-size: var(--font-size-xs);
          color: var(--text-regular);

          .el-icon {
            color: var(--primary-color);
          }
        }
      }

      .specialties {
        width: 18.75rem;

        h4 {
          margin: 0 0 0.75rem 0;
          font-size: var(--font-size-xs);
          color: var(--text-secondary);
        }

        .specialty-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem;
        }
      }
    }

    .patients-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(15.625rem, 1fr));
      gap: 0.75rem;

      .patient-mini-card {
        display: flex;
        align-items: center;
        gap: 0.625rem;
        padding: 0.875rem 1rem;
        background: white;
        border-radius: 0.5rem;
        cursor: pointer;
        transition: all 0.2s;

        &:hover {
          box-shadow: 0 0.25rem 0.75rem rgba(0, 0, 0, 0.08);

          .arrow {
            transform: translateX(0.25rem);
          }
        }

        .el-icon:first-child {
          color: var(--success-color);
        }

        span {
          flex: 1;
          font-weight: 500;
        }

        .arrow {
          color: var(--text-placeholder);
          transition: transform 0.2s;
        }
      }
    }

    .load-more-wrapper {
      margin-top: 1rem;
      display: flex;
      justify-content: center;
    }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(11.25rem, 1fr));
      gap: 1rem;

      .stat-card {
        background: white;
        border-radius: 0.5rem;
        padding: 1.25rem;
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.5rem;

        .stat-value {
          font-size: 1.75rem;
          font-weight: 600;
          color: var(--primary-color);
        }

        .stat-label {
          font-size: 0.8125rem;
          color: var(--text-secondary);
        }
      }
    }

    .patients-evaluation {
      margin-top: 1.5rem;

      h3 {
        margin: 0 0 1rem 0;
          font-size: var(--font-size-lg);
        font-weight: 600;
        color: var(--text-primary);
      }

      .evaluation-cards {
        display: flex;
        flex-direction: column;
        gap: 1rem;
      }
    }

    .loading-placeholder {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 0.75rem;
      padding: 3.75rem 1.25rem;
      color: var(--text-secondary);
    }

    .reflection-tabs {
      background: white;
      border-radius: 0.5rem;
      padding: 1rem;
    }

    .reflection-list {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }
  }

  .loading-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    color: var(--text-secondary);
  }

  .error-state, .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    color: var(--text-secondary);

    h3 {
      margin: 0;
      font-size: 1.125rem;
      color: var(--text-primary);
    }

    p {
      margin: 0;
      font-size: 0.875rem;
    }
  }

  .consultation-error,
  .consultation-empty {
    background: white;
    border: 0.125rem solid var(--border-color);
    padding: 1rem;
    box-shadow: var(--shadow-sm);
    color: var(--text-secondary);
  }

  .consultations-layout {
    display: grid;
    grid-template-columns: minmax(12.5rem, 17.5rem) 1fr;
    gap: 1rem;
  }

  .consultation-patients {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .consultation-patient-card {
    background: white;
    border: 0.125rem solid var(--border-color);
    padding: 0.75rem;
    cursor: pointer;
    box-shadow: var(--shadow-sm);
    transition: transform 0.2s;

    &.active {
      border-color: var(--primary-color);
      box-shadow: var(--shadow-md);
    }

    &:hover {
      transform: translateY(-0.125rem);
    }

    .patient-id {
      font-size: var(--font-size-sm);
      margin-bottom: 0.5rem;
      color: var(--text-primary);
    }

    .patient-meta {
      display: flex;
      justify-content: space-between;
      font-size: var(--font-size-xs);
      color: var(--text-secondary);
    }
  }

  .consultation-thread {
    background: white;
    border: 0.125rem solid var(--border-color);
    box-shadow: var(--shadow-sm);
    display: flex;
    flex-direction: column;
    min-height: 15rem;
  }

  .consultation-thread-header {
    display: flex;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 0.125rem solid var(--border-color);
    font-size: var(--font-size-sm);
  }

  .consultation-thread-body {
    padding: 0.75rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    max-height: 22.5rem;
    overflow-y: auto;
  }

  .consultation-message {
    padding: 0.625rem 0.75rem;
    border: 0.125rem solid var(--border-color-light);
    background: var(--bg-color-overlay);
  }

  .message-meta {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    margin-bottom: 0.375rem;
  }

  .message-tick {
    color: var(--primary-color);
  }

  .message-content {
    font-size: var(--font-size-sm);
    color: var(--text-primary);
    line-height: 1.6;
    white-space: pre-wrap;
  }

  @media (max-width: 56.25rem) {
    .consultations-layout {
      grid-template-columns: 1fr;
    }

    .consultation-thread-body {
      max-height: 17.5rem;
    }
  }
}
</style>
