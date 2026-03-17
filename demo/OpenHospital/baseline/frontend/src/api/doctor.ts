import { request } from './request'
import type {
  DoctorSummary,
  DoctorDetail,
  PatientSummary
} from '@/types'
import type { DoctorConsultationGroup } from '@/types'
import type { DoctorEvaluation } from '@/types/evaluation'

export interface DoctorListParams {
  department?: string
  search?: string
}

export const doctorApi = {
  getDoctors(params?: DoctorListParams): Promise<DoctorSummary[]> {
    return request.get('/doctors', { params })
  },
  getDoctorDetail(doctorId: string): Promise<DoctorDetail> {
    return request.get(`/doctors/${doctorId}`)
  },
  getDoctorPatients(doctorId: string): Promise<PatientSummary[]> {
    return request.get(`/doctors/${doctorId}/patients`)
  },
  getDoctorEvaluation(doctorId: string): Promise<DoctorEvaluation> {
    return request.get(`/doctors/${doctorId}/evaluation`)
  },
  getDoctorConsultations(doctorId: string): Promise<DoctorConsultationGroup[]> {
    return request.get(`/doctors/${doctorId}/consultations`)
  },
  getDoctorMetrics(doctorId: string): Promise<any> {
    return request.get(`/doctors/${doctorId}/metrics`)
  },
  getDoctorStats(doctorId: string): Promise<any> {
    return request.get(`/doctors/${doctorId}/metrics/stats`)
  },
}

export const {
  getDoctors,
  getDoctorDetail,
  getDoctorPatients,
  getDoctorEvaluation,
  getDoctorConsultations,
  getDoctorMetrics,
  getDoctorStats,
} = doctorApi
