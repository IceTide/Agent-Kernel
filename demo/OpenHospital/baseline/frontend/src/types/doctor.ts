export interface Doctor {
  id: string                     // e.g., "Doctor_Cardiology_001"
  name: string                   // e.g., "Dr. James Wilson"
  department: string             // e.g., "Cardiology Department"
  specialties: string[]          // e.g., ["Heart Failure", "Hypertension"]
  consultation_room: string      // e.g., "consultation_cardiology"
  initial_location: string       // e.g., "consultation_cardiology"
  current_status?: DoctorStatus
}

export type DoctorStatus = 'idle' | 'consulting'

export interface DoctorSummary {
  id: string
  name: string
  department: string
  specialties: string[]
  current_status: DoctorStatus
  patient_count: number
}

export interface DoctorDetail extends Omit<Doctor, 'current_status'> {
  current_status: DoctorStatus
  current_patients: PatientSummary[]
}

export interface DoctorStatistics {
  total_patients: number
  diagnosis_accuracy: number
  completed_consultations: number
}
import type { PatientSummary } from './patient'
