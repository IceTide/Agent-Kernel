import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { DoctorSummary, DoctorStatus, DoctorDetail, DoctorConsultationGroup } from '@/types'
import type { DoctorEvaluation } from '@/types/evaluation'
import { doctorApi } from '@/api'

export const useDoctorStore = defineStore('doctor', () => {
  const doctors = ref<DoctorSummary[]>([])
  const currentDoctor = ref<DoctorDetail | null>(null)
  const evaluation = ref<DoctorEvaluation | null>(null)
  const treatmentEvaluations = ref<Record<string, any>>({}) // Key: patient_id, Value: evaluation result
  const consultationGroups = ref<DoctorConsultationGroup[]>([])
  const loading = ref(false)
  const evaluationLoading = ref(false)
  const consultationsLoading = ref(false)
  const error = ref<string | null>(null)
  const consultationsError = ref<string | null>(null)
  const selectedDoctorId = ref<string | null>(null)
  const searchQuery = ref('')
  const selectedDepartment = ref<string | null>(null)
  const filteredDoctors = computed(() => {
    let result = doctors.value

    if (searchQuery.value) {
      const query = searchQuery.value.toLowerCase()
      result = result.filter(d =>
        d.name.toLowerCase().includes(query) ||
        d.id.toLowerCase().includes(query)
      )
    }

    if (selectedDepartment.value) {
      result = result.filter(d => d.department === selectedDepartment.value)
    }

    return result
  })

  const departments = computed(() => {
    const depts = new Set(doctors.value.map(d => d.department))
    return Array.from(depts).sort()
  })
  async function fetchDoctors() {
    loading.value = true
    try {
      const data = await doctorApi.getDoctors()
      doctors.value = data
    } catch (error) {
      console.error('Failed to fetch doctors:', error)
    } finally {
      loading.value = false
    }
  }
  async function silentFetchDoctors() {
    try {
      const data = await doctorApi.getDoctors()
      const newDoctorMap = new Map(data.map(d => [d.id, d]))
      const existingDoctorMap = new Map(doctors.value.map(d => [d.id, d]))
      for (const [id, doctor] of newDoctorMap) {
        const existing = existingDoctorMap.get(id)
        if (existing) {
          Object.assign(existing, doctor)
        } else {
          doctors.value.push(doctor)
        }
      }
      const newDataIds = new Set(data.map(d => d.id))
      doctors.value = doctors.value.filter(d => newDataIds.has(d.id))
    } catch (error) {
      console.debug('Failed to silently fetch doctors:', error)
    }
  }

  async function fetchDoctorDetail(doctorId: string) {
    loading.value = true
    error.value = null

    try {
      const data = await doctorApi.getDoctorDetail(doctorId)
      if (selectedDoctorId.value === doctorId) {
        currentDoctor.value = data
      }
    } catch (err) {
      console.error('Failed to fetch doctor detail:', err)
      if (selectedDoctorId.value === doctorId) {
        error.value = `None法加载Doctor ${doctorId} 的Details`
        currentDoctor.value = null
      }
    } finally {
      if (selectedDoctorId.value === doctorId) {
        loading.value = false
      }
    }
  }

  async function fetchEvaluation(doctorId: string) {
    evaluationLoading.value = true
    try {
      const data = await doctorApi.getDoctorEvaluation(doctorId)
      if (selectedDoctorId.value === doctorId) {
        evaluation.value = data
      }
    } catch (err) {
      console.error('Failed to fetch evaluation:', err)
    } finally {
      evaluationLoading.value = false
    }
  }

  async function fetchDoctorConsultations(doctorId: string) {
    consultationsLoading.value = true
    consultationsError.value = null
    try {
      const data = await doctorApi.getDoctorConsultations(doctorId)
      if (selectedDoctorId.value === doctorId) {
        consultationGroups.value = data
      }
    } catch (err) {
      console.error('Failed to fetch doctor consultations:', err)
      if (selectedDoctorId.value === doctorId) {
        consultationsError.value = '无法加载会诊对话'
        consultationGroups.value = []
      }
    } finally {
      consultationsLoading.value = false
    }
  }

  function selectDoctor(doctorId: string) {
    if (selectedDoctorId.value === doctorId && currentDoctor.value?.id === doctorId) {
      return
    }

    selectedDoctorId.value = doctorId
    currentDoctor.value = null
    evaluation.value = null
    consultationGroups.value = []
    error.value = null
    fetchDoctorDetail(doctorId)
    fetchEvaluation(doctorId)
    fetchDoctorConsultations(doctorId)
  }

  function updateDoctorStatus(doctorId: string, status: string) {
    const doctor = doctors.value.find(d => d.id === doctorId)
    if (doctor && status) {
      doctor.current_status = status as DoctorStatus
    }
  }

  function clearSelection() {
    selectedDoctorId.value = null
    currentDoctor.value = null
    evaluation.value = null
    consultationGroups.value = []
  }
  async function refreshCurrentDoctor() {
    if (!selectedDoctorId.value) return

    const doctorId = selectedDoctorId.value

    try {
      const [doctorData, evaluationData, consultationData] = await Promise.all([
        doctorApi.getDoctorDetail(doctorId),
        doctorApi.getDoctorEvaluation(doctorId).catch(() => null),
        doctorApi.getDoctorConsultations(doctorId).catch(() => null)
      ])
      if (selectedDoctorId.value === doctorId) {
        currentDoctor.value = doctorData
        if (evaluationData) {
          evaluation.value = evaluationData
        }
        if (consultationData) {
          consultationGroups.value = consultationData
        }
      }
    } catch (err) {
      console.debug('Failed to refresh doctor detail:', err)
    }
  }

  function setTreatmentEvaluation(patientId: string, result: any) {
    treatmentEvaluations.value[patientId] = result
  }

  return {
    doctors,
    currentDoctor,
    evaluation,
    treatmentEvaluations,
    consultationGroups,
    loading,
    evaluationLoading,
    consultationsLoading,
    error,
    consultationsError,
    selectedDoctorId,
    searchQuery,
    selectedDepartment,
    filteredDoctors,
    departments,
    fetchDoctors,
    silentFetchDoctors,
    fetchDoctorDetail,
    fetchEvaluation,
    fetchDoctorConsultations,
    selectDoctor,
    updateDoctorStatus,
    clearSelection,
    refreshCurrentDoctor,
    setTreatmentEvaluation,
  }
})
