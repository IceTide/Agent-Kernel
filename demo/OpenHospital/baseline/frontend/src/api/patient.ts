import { request } from './request'
import type { 
  PatientSummary, 
  PatientDetail, 
  PatientPhase,
  TrajectoryEvent 
} from '@/types'

export interface PatientListParams {
  phase?: PatientPhase
  department?: string
  search?: string
}

export const patientApi = {
  getPatients(params?: PatientListParams): Promise<PatientSummary[]> {
    return request.get('/patients', { params })
  },
  getPatientDetail(patientId: string): Promise<PatientDetail> {
    return request.get(`/patients/${patientId}`)
  },
  getPatientTrajectory(patientId: string): Promise<TrajectoryEvent[]> {
    return request.get(`/patients/${patientId}/trajectory`)
  },
}
