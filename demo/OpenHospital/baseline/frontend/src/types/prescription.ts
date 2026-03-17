export interface PrescriptionRecord {
  id: string
  patient_id: string
  doctor_id: string
  diagnosis: string           // Diagnosis
  treatment_plan: string      // Treatment Plan
  prescribed_tick: number
  status: PrescriptionStatus
  completed_tick?: number
  treatment_result?: TreatmentResult
}

export type PrescriptionStatus = 'pending' | 'completed'

export interface TreatmentResult {
  success: boolean
  score: number
  feedback: string
}

