import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { PatientSummary, PatientPhase, PatientDetail } from '@/types'
import { patientApi } from '@/api'

export const usePatientStore = defineStore('patient', () => {
  const patients = ref<PatientSummary[]>([])
  const currentPatient = ref<PatientDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const selectedPatientId = ref<string | null>(null)
  const searchQuery = ref('')
  const selectedPhase = ref<PatientPhase | null>(null)
  const selectedDepartment = ref<string | null>(null)
  const filteredPatients = computed(() => {
    let result = patients.value
    
    if (searchQuery.value) {
      const query = searchQuery.value.toLowerCase()
      result = result.filter(p => 
        p.name.toLowerCase().includes(query) ||
        p.id.toLowerCase().includes(query)
      )
    }
    
    if (selectedPhase.value) {
      result = result.filter(p => p.current_phase === selectedPhase.value)
    }
    
    if (selectedDepartment.value) {
      result = result.filter(p => p.department === selectedDepartment.value)
    }
    
    return result
  })
  
  const patientsByPhase = computed(() => {
    const grouped: Record<PatientPhase, PatientSummary[]> = {
      idle: [],
      home: [],
      registered: [],
      consulting: [],
      examined: [],
      treated: [],
      finish: [],
    }

    patients.value.forEach(p => {
      const phase = p.current_phase || 'idle'
      if (grouped[phase]) {
        grouped[phase].push(p)
      }
    })

    return grouped
  })
  async function fetchPatients() {
    loading.value = true
    try {
      const data = await patientApi.getPatients()
      patients.value = data
    } catch (error) {
      console.error('Failed to fetch patients:', error)
    } finally {
      loading.value = false
    }
  }
  async function silentFetchPatients() {
    try {
      const data = await patientApi.getPatients()
      const newPatientMap = new Map(data.map(p => [p.id, p]))
      const existingPatientMap = new Map(patients.value.map(p => [p.id, p]))
      for (const [id, patient] of newPatientMap) {
        const existing = existingPatientMap.get(id)
        if (existing) {
          Object.assign(existing, patient)
        } else {
          patients.value.push(patient)
        }
      }
      const newDataIds = new Set(data.map(p => p.id))
      patients.value = patients.value.filter(p => newDataIds.has(p.id))
    } catch (error) {
      console.debug('Failed to silently fetch patients:', error)
    }
  }
  
  async function fetchPatientDetail(patientId: string) {
    loading.value = true
    error.value = null
    
    try {
      const data = await patientApi.getPatientDetail(patientId)
      if (selectedPatientId.value === patientId) {
        currentPatient.value = data
      }
    } catch (err) {
      console.error('Failed to fetch patient detail:', err)
      if (selectedPatientId.value === patientId) {
        error.value = `None法加载Patient ${patientId} 的Details`
        currentPatient.value = null
      }
    } finally {
      if (selectedPatientId.value === patientId) {
        loading.value = false
      }
    }
  }
  
  function selectPatient(patientId: string) {
    if (selectedPatientId.value === patientId && currentPatient.value?.id === patientId) {
      return
    }

    selectedPatientId.value = patientId
    loading.value = true
    currentPatient.value = null
    error.value = null
    fetchPatientDetail(patientId)
  }
  
  function updatePatientPhase(patientId: string, phase: PatientPhase) {
    const patient = patients.value.find(p => p.id === patientId)
    if (patient) {
      patient.current_phase = phase
    }
    if (currentPatient.value?.id === patientId) {
      currentPatient.value.current_phase = phase
      if (currentPatient.value.state) {
        currentPatient.value.state.current_phase = phase
      }
    }
  }
  
  function updatePatientDoctor(patientId: string, doctorId: string, department: string) {
    const patient = patients.value.find(p => p.id === patientId)
    if (patient) {
      patient.assigned_doctor = doctorId
      patient.department = department
    }
    if (currentPatient.value?.id === patientId) {
      currentPatient.value.assigned_doctor = doctorId
      currentPatient.value.department = department
    }
  }
  
  function clearSelection() {
    selectedPatientId.value = null
    currentPatient.value = null
  }
  async function refreshCurrentPatient() {
    if (!selectedPatientId.value) return
    
    const patientId = selectedPatientId.value
    
    try {
      const data = await patientApi.getPatientDetail(patientId)
      if (selectedPatientId.value === patientId) {
        currentPatient.value = data
      }
    } catch (err) {
      console.debug('Failed to refresh patient detail:', err)
    }
  }
  
  return {
    patients,
    currentPatient,
    loading,
    error,
    selectedPatientId,
    searchQuery,
    selectedPhase,
    selectedDepartment,
    filteredPatients,
    patientsByPhase,
    fetchPatients,
    silentFetchPatients,
    fetchPatientDetail,
    selectPatient,
    updatePatientPhase,
    updatePatientDoctor,
    clearSelection,
    refreshCurrentPatient,
  }
})
