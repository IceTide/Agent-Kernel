export interface Diagnosis {
    predicted: string
    expected: string
    correct: boolean
    available: boolean
}

export interface Examination {
    ordered_tick: number
    items: string[]
    expected_items: string[]
    precision: number
    has_ground_truth: boolean
}

export interface Treatment {
    provided: boolean
    diagnosis: string
    treatment_plan: string
}

export interface PatientEvaluation {
    patient_id: string
    patient_name: string
    diagnosis: Diagnosis
    examinations: Examination[]
    examination_precision: number
    treatment: Treatment
}

export interface EvaluationSummary {
    total_patients: number
    total_diagnoses: number
    correct_diagnoses: number
    diagnosis_accuracy: number
    total_examinations: number
    average_examination_precision: number
    has_ground_truth: boolean
}

export interface DoctorEvaluation {
    doctor_id: string
    doctor_name: string
    department: string
    summary: EvaluationSummary
    patients: PatientEvaluation[]
}

