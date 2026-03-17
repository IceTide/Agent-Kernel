<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { ScrollbarInstance } from 'element-plus'
import { ChatDotSquare, CircleCheck } from '@element-plus/icons-vue'

interface Message {
  id: string
  role: 'doctor' | 'patient'
  content: string
  timestamp: Date
  type?: 'text' | 'examination' | 'diagnosis'
}

interface Props {
  visible: boolean
  patientName: string
  patientId?: string
}

const props = defineProps<Props>()
const emit = defineEmits(['update:visible', 'close'])

const scrollbarRef = ref<ScrollbarInstance | null>(null)
const messages = ref<Message[]>([])
const inputText = ref('')
const selectedExamination = ref('')
const selectedDisease = ref('')
const treatmentPlan = ref('')
const examinationResults = ref<Array<{ name: string; result: string; timestamp: Date }>>([])
const showExaminationResults = ref(false)
const patientProfile = ref<any>(null)
const groundTruth = ref<any>(null)
const mockPatientData: Record<string, any> = {
  'Patient_02912': {
    patient_id: 'Patient_02912',
    patient_ontology: {
      demographics: {
        name: 'Dylan Weaver',
        age: 40,
        gender: 'Male',
        marital_status: 'Married',
        occupation: 'Astronomy student'
      },
      present_illness_history: {
        chief_complaint: 'Five days ago, I started getting sharp aching pain on the outside of my right elbow after using tools all day. It\'s gotten worse, and I\'ve been sleeping poorly because of it.',
        symptoms_and_progression: 'Pain is localized to the lateral elbow with occasional warmth and tenderness to touch. Initially mild soreness only when lifting or twisting, but over several days progressed to pain with wrist extension and making a tight fist; now he notices reduced grip strength and difficulty holding a mug, turning a screwdriver, and opening jar lids. Intermittent clicking sensation is noted with forearm rotation. Accompanied by morning stiffness around the elbow and waking at night once due to pain. No numbness or tingling in the hand, no neck pain radiating down the arm, no hand color change, no swelling of the entire joint, no fever, and no recent direct blow to the elbow.',
        current_general_status: {
          diet: 'Ingredient-conscious; reads food labels and tries to keep a balanced diet with adequate protein and vegetables.',
          sleep: 'Light and interrupted over the past week due to anxiety and occasional elbow pain at night.',
          excretion: 'Normal bowel and urinary habits.',
          weight_change: 'No significant recent weight change.'
        }
      },
      medical_history: {
        previous_diseases: ['Intermittent low back pain related to prior physical training', 'Seasonal allergic rhinitis'],
        long_term_medication: 'None on a daily basis; uses over-the-counter ibuprofen as needed for pain.',
        surgery_or_trauma: 'None; reports past musculoskeletal strains during athletic training without fractures.',
        allergies: {
          food: [],
          drug: []
        }
      },
      personal_history: {
        smoking: 'Never smoker.',
        alcohol: 'Occasional alcohol use on weekends; denies heavy use.'
      },
      family_history: {
        similar_illness: 'None.',
        hereditary_diseases: 'Father with hypertension; otherwise none known.'
      }
    },
    request_examinations: [
      {
        item_name: 'Magnetic Resonance Imaging (MRI)',
        result: 'Right elbow MRI: common extensor tendon thickening with increased T2 signal at lateral epicondyle; partial-thickness tear; mild peritendinous edema.'
      }
    ]
  },
  'Patient_Comorbid-00272': {
    patient_id: 'Patient_Comorbid-00272',
    patient_ontology: {
      demographics: {
        name: 'Sarah Parker',
        age: 32,
        gender: 'Male',
        marital_status: 'Widowed',
        occupation: 'Educator (history)'
      },
      present_illness_history: {
        chief_complaint: 'I\'ve been experiencing recurrent sore throat and fatigue for several weeks now. I also feel weak and tired all the time.',
        symptoms_and_progression: 'Persistent sore throat with difficulty swallowing, chronic fatigue, weakness, and pale appearance. Symptoms have been ongoing for about 5 weeks.',
        current_general_status: {
          diet: 'Decreased appetite; eating smaller meals due to early satiety; tolerates fluids.',
          sleep: 'Poor sleep due to discomfort.',
          excretion: 'No change in bowel habits.',
          weight_change: 'Unintentional loss of about 4 kg over 5 weeks.'
        }
      },
      medical_history: {
        previous_diseases: ['Recurrent sinus infections', 'Childhood asthma (inactive)'],
        long_term_medication: 'None. Uses acetaminophen as needed.',
        surgery_or_trauma: 'Appendectomy at age 17.',
        allergies: {
          food: [],
          drug: ['Penicillin (pruritic rash)']
        }
      },
      personal_history: {
        smoking: 'Never smoker.',
        alcohol: 'Occasional alcohol, about 1-2 drinks on weekends.'
      },
      family_history: {
        similar_illness: 'Father treated for lymphoma in his late 50s; currently in remission.',
        hereditary_diseases: 'Mother with hypertension.'
      }
    },
    request_examinations: [
      {
        item_name: 'Complete Blood Count (CBC)',
        result: 'WBC: 7.5 K/uL, RBC: 4.2 M/uL, Hemoglobin: 11.8 g/dL (low), Hematocrit: 35%, MCV: 78 fL (low - microcytic), Platelets: 245 K/uL'
      },
      {
        item_name: 'Iron Studies',
        result: 'Serum Iron: 35 μg/dL (low), TIBC: 420 μg/dL (high), Transferrin Saturation: 8% (low), Ferritin: 12 ng/mL (low)'
      }
    ]
  }
}
const examinations = ref<string[]>([
  'Complete Blood Count (CBC)',
  'Iron Studies',
  'Vitamin and Mineral Assay',
  'Stool Routine Test',
  'Esophagogastroduodenoscopy (EGD)',
  'Colonoscopy',
  'Laryngoscopy',
  'X-Ray',
  'CT Scan',
  'MRI',
  'Ultrasound',
  'ECG'
])

const diseases = ref<string[]>([
  'Tennis elbow',
  'Chronic Pharyngitis',
  'Iron deficiency anemia',
  'Hypertension',
  'Diabetes',
  'Asthma',
  'Gastroesophageal Reflux Disease (GERD)',
  'Migraine',
  'Common Cold',
  'Flu'
])
async function loadPatientData() {
  if (!props.patientId) return

  try {
    if (mockPatientData[props.patientId]) {
      patientProfile.value = mockPatientData[props.patientId]
      console.log('Loaded mock patient data for', props.patientId)
    }
    const gtResponse = await fetch('/data/ground_truth/ground_truth.json')
    if (gtResponse.ok) {
      const gtData = await gtResponse.json()
      groundTruth.value = gtData[props.patientId]
      if (groundTruth.value?.necessary_examinations) {
        examinations.value = [
          ...groundTruth.value.necessary_examinations,
          'Musculoskeletal Ultrasound (MSKUS)',
          'X-Ray',
          'CT Scan',
          'Ultrasound',
          'ECG',
          'Blood Pressure Monitoring',
          'Complete Blood Count (CBC)'
        ]
      }
      if (groundTruth.value?.final_diagnosis) {
        const realDiagnosis = Array.isArray(groundTruth.value.final_diagnosis)
          ? groundTruth.value.final_diagnosis
          : [groundTruth.value.final_diagnosis]

        diseases.value = [
          ...realDiagnosis,
          'Lateral Epicondylitis (Tennis Elbow)',
          'Medial Epicondylitis (Golfer\'s Elbow)',
          'Carpal Tunnel Syndrome',
          'Rotator Cuff Injury',
          'Tendinitis',
          'Bursitis',
          'Arthritis',
          'Nerve Compression',
          'Muscle Strain'
        ]
      }
    }
    if (!patientProfile.value) {
      const profileResponse = await fetch('/data/patients/profiles_all.jsonl')
      if (profileResponse.ok) {
        const profileText = await profileResponse.text()
        const profiles = profileText.split('\n').filter(line => line.trim())
        for (const line of profiles) {
          try {
            const profile = JSON.parse(line)
            if (profile.id === props.patientId || profile.patient_id === props.patientId) {
              patientProfile.value = profile
              console.log('Loaded patient profile from profiles_all.jsonl')
              break
            }
          } catch (e) {
          }
        }
      }
    }

    console.log('Patient profile loaded:', patientProfile.value ? 'Yes' : 'No')
  } catch (error) {
    console.warn('Failed to load patient data:', error)
  }
}
function generatePatientReply(doctorMessage: string): string {
  if (!patientProfile.value) {
    return 'I understand. Is there anything else you need to know?'
  }

  const lowerMessage = doctorMessage.toLowerCase()
  const profile = patientProfile.value
  const ontology = profile.patient_ontology || profile
  const symptoms = ontology.present_illness_history?.symptoms_and_progression || ''
  const chiefComplaint = ontology.present_illness_history?.chief_complaint || ''
  if (lowerMessage.includes('grip') || lowerMessage.includes('twist') || lowerMessage.includes('lift')) {
    if (symptoms.includes('grip') || symptoms.includes('twist') || chiefComplaint.includes('tool')) {
      return 'Yes, it gets worse when I grip things, twist doorknobs, or lift anything—even holding a mug is hard now. No numbness or tingling in my hand or fingers.'
    }
  }

  if (lowerMessage.includes('numb') || lowerMessage.includes('tingling') || lowerMessage.includes('weakness')) {
    if (symptoms.includes('No numbness') || symptoms.includes('no tingling')) {
      return 'No numbness or tingling in my hand or fingers.'
    }
    return 'No, I don\'t have any numbness, tingling, or weakness.'
  }

  if (lowerMessage.includes('when') && (lowerMessage.includes('start') || lowerMessage.includes('begin'))) {
    if (chiefComplaint.includes('days ago')) {
      const match = chiefComplaint.match(/(\d+)\s+days?\s+ago/)
      if (match) {
        return `It started ${match[1]} days ago.`
      }
    }
    return chiefComplaint || 'It started recently.'
  }

  if (lowerMessage.includes('worse') || lowerMessage.includes('better') || lowerMessage.includes('change')) {
    if (symptoms.includes('progressed')) {
      return 'It\'s gotten worse over time. What started as mild soreness is now affecting my daily activities.'
    }
    return 'It\'s been getting worse.'
  }

  if (lowerMessage.includes('pain') && (lowerMessage.includes('where') || lowerMessage.includes('location'))) {
    if (chiefComplaint.includes('elbow')) {
      return 'The pain is on the outside of my right elbow.'
    }
    return chiefComplaint || 'I have pain in the affected area.'
  }
  if (lowerMessage.includes('sleep') || lowerMessage.includes('rest')) {
    return ontology.present_illness_history?.current_general_status?.sleep ||
           'My sleep has been okay, nothing unusual.'
  }

  if (lowerMessage.includes('diet') || lowerMessage.includes('eat') || lowerMessage.includes('appetite')) {
    return ontology.present_illness_history?.current_general_status?.diet ||
           'My diet is quite regular.'
  }

  if (lowerMessage.includes('weight')) {
    return ontology.present_illness_history?.current_general_status?.weight_change ||
           'My weight has been stable.'
  }

  if (lowerMessage.includes('symptom') || lowerMessage.includes('feel') || lowerMessage.includes('problem')) {
    return symptoms || chiefComplaint || 'I haven\'t been feeling well lately.'
  }

  if (lowerMessage.includes('history') || lowerMessage.includes('before') || lowerMessage.includes('past')) {
    const prevDiseases = ontology.medical_history?.previous_diseases || []
    if (prevDiseases.length > 0) {
      return `I have a history of ${prevDiseases.join(', ')}.`
    }
    return 'No significant medical history.'
  }

  if (lowerMessage.includes('medication') || lowerMessage.includes('drug') || lowerMessage.includes('medicine')) {
    return ontology.medical_history?.long_term_medication || 'I\'m not taking any regular medications.'
  }

  if (lowerMessage.includes('allerg')) {
    const allergies = ontology.medical_history?.allergies
    if (allergies?.drug?.length > 0 || allergies?.food?.length > 0) {
      const allergyList = [
        ...(allergies.drug || []).map((d: string) => `drug: ${d}`),
        ...(allergies.food || []).map((f: string) => `food: ${f}`)
      ]
      return `Yes, I have allergies to: ${allergyList.join(', ')}.`
    }
    return 'No known allergies.'
  }

  if (lowerMessage.includes('smoke') || lowerMessage.includes('tobacco')) {
    return ontology.personal_history?.smoking || 'I don\'t smoke.'
  }

  if (lowerMessage.includes('alcohol') || lowerMessage.includes('drink')) {
    return ontology.personal_history?.alcohol || 'I drink occasionally.'
  }

  if (lowerMessage.includes('family') || lowerMessage.includes('parent') || lowerMessage.includes('relative')) {
    const familyHistory = ontology.family_history?.similar_illness || ontology.family_history?.hereditary_diseases
    if (familyHistory) {
      return familyHistory
    }
    return 'No significant family history.'
  }
  return 'I understand. What else would you like to know?'
}
watch(() => props.visible, (newVal) => {
  if (newVal) {
    if (messages.value.length === 0) {
      loadPatientData().then(() => {
        setTimeout(() => {
          const ontology = patientProfile.value?.patient_ontology || patientProfile.value
          const patientName = ontology?.demographics?.name?.split(' ')[0] || props.patientName
          const chiefComplaint = ontology?.present_illness_history?.chief_complaint ||
                                'I haven\'t been feeling well lately.'
          const initialMessage = `I'm ${patientName}. ${chiefComplaint}`
          addMessage('patient', initialMessage)
        }, 500)
      })
    }
  }
})

function addMessage(role: 'doctor' | 'patient', content: string, type: 'text' | 'examination' | 'diagnosis' = 'text') {
  const message: Message = {
    id: Date.now().toString() + Math.random(),
    role,
    content,
    timestamp: new Date(),
    type
  }
  messages.value.push(message)
  nextTick(() => {
    scrollToBottom()
  })
}

function scrollToBottom() {
  if (scrollbarRef.value) {
    nextTick(() => {
      const wrapEl = scrollbarRef.value?.wrapRef
      if (wrapEl) {
        scrollbarRef.value?.setScrollTop(wrapEl.scrollHeight)
      }
    })
  }
}

function sendMessage() {
  if (!inputText.value.trim()) return

  const message = inputText.value.trim()
  addMessage('doctor', message)
  setTimeout(() => {
    const reply = generatePatientReply(message)
    addMessage('patient', reply)
  }, 800)

  inputText.value = ''
}

function orderExamination() {
  if (!selectedExamination.value) return

  const examName = selectedExamination.value
  setTimeout(() => {
    const mockResult = generateExaminationResult(examName)
    examinationResults.value.push({
      name: examName,
      result: mockResult,
      timestamp: new Date()
    })
    showExaminationResults.value = true
  }, 1000)

  selectedExamination.value = ''
}

function generateExaminationResult(examName: string): string {
  if (patientProfile.value?.request_examinations) {
    const realExam = patientProfile.value.request_examinations.find(
      (exam: any) => exam.item_name === examName
    )
    if (realExam?.result) {
      return realExam.result
    }
  }
  const defaultResults: Record<string, string> = {
    'Complete Blood Count (CBC)': 'WBC: 7.5 K/uL, RBC: 4.2 M/uL, Hemoglobin: 11.8 g/dL (low), Hematocrit: 35%, MCV: 78 fL (low - microcytic), Platelets: 245 K/uL',
    'Iron Studies': 'Serum Iron: 35 μg/dL (low), TIBC: 420 μg/dL (high), Transferrin Saturation: 8% (low), Ferritin: 12 ng/mL (low)',
    'Vitamin and Mineral Assay': 'Vitamin B12: 180 pg/mL (low-normal), Folate: 3.2 ng/mL (low), Vitamin D: 22 ng/mL (insufficient)',
    'Stool Routine Test': 'No blood detected, normal consistency, no parasites identified',
    'Esophagogastroduodenoscopy (EGD)': 'Mild erythema and edema of the distal esophageal mucosa consistent with reflux esophagitis; no ulcers or masses; gastric and duodenal mucosa appear normal',
    'Colonoscopy': 'Normal colonic mucosa throughout; no polyps, masses, or bleeding sources identified',
    'Laryngoscopy': 'Posterior pharyngeal wall shows mild erythema and granularity consistent with chronic pharyngitis; vocal cords mobile and appear normal',
    'Magnetic Resonance Imaging (MRI)': 'Right elbow MRI: common extensor tendon thickening with increased T2 signal at lateral epicondyle; partial-thickness tear; mild peritendinous edema.',
    'Musculoskeletal Ultrasound (MSKUS)': 'Ultrasound shows thickening and hypoechogenicity of the common extensor tendon at the lateral epicondyle, consistent with tendinosis. No complete tear identified.',
    'X-Ray': 'X-ray shows no fracture or dislocation; soft tissue swelling noted',
    'CT Scan': 'CT scan reveals no significant abnormalities in the scanned area',
    'Ultrasound': 'Ultrasound examination shows normal organ structure and function',
    'ECG': 'ECG shows normal sinus rhythm, heart rate 72 bpm, no arrhythmias detected',
    'Blood Pressure Monitoring': 'Blood pressure: 118/76 mmHg (normal)'
  }

  return defaultResults[examName] || 'Examination completed, results within normal range'
}

function sendDiagnosis() {
  if (!selectedDisease.value || !treatmentPlan.value.trim()) return

  const diagnosisText = `Diagnosis: ${selectedDisease.value}\nTreatment Plan: ${treatmentPlan.value}`
  addMessage('doctor', diagnosisText, 'diagnosis')
  setTimeout(() => {
    addMessage('patient', 'Thank you, doctor. I will follow your treatment plan.')
  }, 1000)

  selectedDisease.value = ''
  treatmentPlan.value = ''
}

function closeDialog() {
  emit('update:visible', false)
  emit('close')
}
</script>

<template>
  <div v-if="visible" class="consultation-dialog-overlay" @click.self="closeDialog">
    <div class="consultation-dialog" @click.stop>
      <div class="window-frame">
        <div class="window-titlebar">
          <div class="window-title">
            <el-icon><ChatDotSquare /></el-icon>
            <span>Doctor Consultation - {{ patientName }}</span>
          </div>
          <div class="window-controls">
            <div class="control-btn minimize">_</div>
            <div class="control-btn maximize">□</div>
            <div class="control-btn close" @click="closeDialog">×</div>
          </div>
        </div>
        <div class="window-content">
          <el-scrollbar ref="scrollbarRef" class="message-scroll">
            <div class="message-list">
              <div
                v-for="message in messages"
                :key="message.id"
                class="message-item"
                :class="message.role"
              >
                <div class="message-header">
                  <span class="message-role">{{ message.role === 'doctor' ? 'Doctor' : patientName }}</span>
                  <span class="message-time">{{ message.timestamp.toLocaleTimeString() }}</span>
                </div>
                <div class="message-content" :class="message.type">
                  {{ message.content }}
                </div>
              </div>
            </div>
          </el-scrollbar>
          <div class="input-area">
            <div v-if="examinationResults.length > 0" class="examination-results-panel">
              <div class="panel-header">
                <span>Examination Results ({{ examinationResults.length }})</span>
                <button class="toggle-btn" @click="showExaminationResults = !showExaminationResults">
                  {{ showExaminationResults ? '▼' : '▶' }}
                </button>
              </div>
              <div v-show="showExaminationResults" class="results-list">
                <div
                  v-for="(exam, index) in examinationResults"
                  :key="index"
                  class="result-item"
                >
                  <div class="result-header">
                    <strong>{{ exam.name }}</strong>
                    <span class="result-time">{{ exam.timestamp.toLocaleTimeString() }}</span>
                  </div>
                  <div class="result-content">{{ exam.result }}</div>
                </div>
              </div>
            </div>

            <div class="input-row">
              <input
                v-model="inputText"
                type="text"
                class="text-input"
                placeholder="Type your message..."
                @keyup.enter="sendMessage"
              />
              <button class="send-btn" @click="sendMessage">Send</button>
            </div>
            <div class="action-row">
              <div class="action-group">
                <label class="action-label">Examination:</label>
                <select v-model="selectedExamination" class="action-select">
                  <option value="">Select...</option>
                  <option v-for="exam in examinations" :key="exam" :value="exam">
                    {{ exam }}
                  </option>
                </select>
                <button class="action-btn" @click="orderExamination" :disabled="!selectedExamination">
                  Order
                </button>
              </div>

              <div class="action-group">
                <label class="action-label">Diagnosis:</label>
                <select v-model="selectedDisease" class="action-select">
                  <option value="">Select disease...</option>
                  <option v-for="disease in diseases" :key="disease" :value="disease">
                    {{ disease }}
                  </option>
                </select>
                <input
                  v-model="treatmentPlan"
                  type="text"
                  class="treatment-input"
                  placeholder="Treatment plan..."
                />
                <button class="action-btn" @click="sendDiagnosis" :disabled="!selectedDisease || !treatmentPlan">
                  Send
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="window-statusbar">
          <div class="status-info">
            <el-icon class="status-icon"><CircleCheck /></el-icon>
            <span>{{ messages.length }} messages</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.consultation-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}

.consultation-dialog {
  width: 95%;
  max-width: 70rem;
  height: 90vh;
  max-height: 60rem;
}

.window-frame {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f0f0f0;
  border: 0.1875rem solid #c0c0c0;
  box-shadow:
    inset -0.0625rem -0.0625rem 0 #808080,
    inset 0.0625rem 0.0625rem 0 #ffffff,
    0.5rem 0.5rem 0 rgba(0, 0, 0, 0.3);

  .window-titlebar {
    background: linear-gradient(180deg, #0078d4 0%, #0066b8 100%);
    padding: 0.25rem 0.375rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 0.125rem solid #0052a3;
    min-height: 2rem;
    flex-shrink: 0;

    .window-title {
      display: flex;
      align-items: center;
      gap: 0.375rem;
      color: white;
      font-size: 1rem;
      font-weight: 600;

      .el-icon {
        font-size: 1rem;
      }
    }

    .window-controls {
      display: flex;
      gap: 0.125rem;

      .control-btn {
        width: 1.25rem;
        height: 1.25rem;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #e0e0e0;
        border: 0.125rem solid;
        border-color: #ffffff #808080 #808080 #ffffff;
        font-size: 0.875rem;
        font-weight: bold;
        cursor: pointer;
        user-select: none;
        line-height: 1;
        padding-bottom: 0.125rem;

        &:hover {
          background: #f0f0f0;
        }

        &:active {
          border-color: #808080 #ffffff #ffffff #808080;
          background: #d0d0d0;
        }

        &.close {
          color: #000;
          font-size: 1.125rem;
          line-height: 0.9;

          &:hover {
            background: #e81123;
            color: white;
            border-color: #e81123;
          }
        }
      }
    }
  }

  .window-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: #ffffff;
    border: 0.125rem solid #d4d4d4;
    border-top: none;
    min-height: 0;
    overflow: hidden;
    height: 100%;

    .message-scroll {
      flex: 1;
      min-height: 20rem;
      height: 100%;

      :deep(.el-scrollbar__wrap) {
        background: #fafafa;
        max-height: 100%;
      }

      :deep(.el-scrollbar__view) {
        min-height: 100%;
      }

      :deep(.el-scrollbar__bar) {
        background: #e0e0e0;
        border: 0.125rem solid;
        border-color: #ffffff #808080 #808080 #ffffff;
        width: 1rem !important;
      }

      :deep(.el-scrollbar__thumb) {
        background: #c0c0c0;
        border: 0.125rem solid;
        border-color: #ffffff #808080 #808080 #ffffff;

        &:hover {
          background: #b0b0b0;
        }
      }
    }

    .message-list {
      padding: 1rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      min-height: 100%;
      width: 100%;

      .message-item {
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
        max-width: 70%;

        &.doctor {
          align-self: flex-end;

          .message-content {
            background: #0078d4;
            color: white;
            border-color: #0052a3 #ffffff #ffffff #0052a3;
          }
        }

        &.patient {
          align-self: flex-start;

          .message-content {
            background: #e0e0e0;
            color: #000;
          }
        }

        .message-header {
          display: flex;
          justify-content: space-between;
          font-size: 0.75rem;
          color: #666;
          padding: 0 0.25rem;

          .message-role {
            font-weight: bold;
          }
        }

        .message-content {
          padding: 0.75rem 1rem;
          border: 0.125rem solid;
          border-color: #ffffff #808080 #808080 #ffffff;
          font-size: 0.9rem;
          line-height: 1.5;
          word-wrap: break-word;
          white-space: pre-wrap;

          &.examination {
            background: #fff3cd !important;
            color: #856404 !important;
            border-color: #ffc107 !important;
          }

          &.diagnosis {
            background: #d4edda !important;
            color: #155724 !important;
            border-color: #28a745 !important;
          }
        }
      }
    }

    .input-area {
      border-top: 0.125rem solid #d4d4d4;
      background: #f0f0f0;
      padding: 0.75rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      flex-shrink: 0;
      max-height: 40%;
      overflow-y: auto;

      .examination-results-panel {
        background: #fff;
        border: 0.125rem solid;
        border-color: #ffffff #808080 #808080 #ffffff;
        margin-bottom: 0.5rem;

        .panel-header {
          background: #0078d4;
          color: white;
          padding: 0.5rem 0.75rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 0.85rem;
          font-weight: bold;

          .toggle-btn {
            background: transparent;
            border: none;
            color: white;
            cursor: pointer;
            font-size: 0.85rem;
            padding: 0 0.25rem;

            &:hover {
              background: rgba(255, 255, 255, 0.1);
            }
          }
        }

        .results-list {
          max-height: 12rem;
          overflow-y: auto;
          padding: 0.75rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;

          .result-item {
            background: #fafafa;
            border: 0.125rem solid #d4d4d4;
            padding: 0.6rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;

            .result-header {
              display: flex;
              justify-content: space-between;
              align-items: center;
              font-size: 0.85rem;

              strong {
                color: #0078d4;
              }

              .result-time {
                font-size: 0.75rem;
                color: #666;
              }
            }

            .result-content {
              font-size: 0.8rem;
              color: #333;
              line-height: 1.5;
              padding: 0.5rem;
              background: #fff;
              border: 0.0625rem solid #e0e0e0;
            }
          }
        }
      }

      .input-row {
        display: flex;
        gap: 0.5rem;

        .text-input {
          flex: 1;
          padding: 0.5rem 0.6rem;
          border: 0.125rem solid;
          border-color: #808080 #ffffff #ffffff #808080;
          background: #ffffff;
          font-size: 0.85rem;
          font-family: 'MS Sans Serif', sans-serif;

          &:focus {
            outline: none;
            border-color: #0078d4;
          }
        }

        .send-btn {
          min-width: 3.5rem;
          padding: 0.5rem 0.75rem;
          border: 0.125rem solid;
          border-color: #ffffff #808080 #808080 #ffffff;
          background: #c0c0c0;
          font-size: 0.85rem;
          font-weight: bold;
          cursor: pointer;
          font-family: 'MS Sans Serif', sans-serif;

          &:hover {
            background: #e0e0e0;
          }

          &:active {
            border-color: #808080 #ffffff #ffffff #808080;
            background: #d0d0d0;
          }
        }
      }

      .action-row {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;

        .action-group {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          flex-wrap: wrap;

          .action-label {
            font-size: 0.8rem;
            font-weight: bold;
            color: #000;
            min-width: 4.5rem;
          }

          .action-select {
            padding: 0.4rem 0.5rem;
            border: 0.125rem solid;
            border-color: #808080 #ffffff #ffffff #808080;
            background: #ffffff;
            font-size: 0.8rem;
            font-family: 'MS Sans Serif', sans-serif;
            min-width: 7rem;

            &:focus {
              outline: none;
              border-color: #0078d4;
            }
          }

          .treatment-input {
            flex: 1;
            padding: 0.4rem 0.5rem;
            border: 0.125rem solid;
            border-color: #808080 #ffffff #ffffff #808080;
            background: #ffffff;
            font-size: 0.8rem;
            font-family: 'MS Sans Serif', sans-serif;
            min-width: 8rem;

            &:focus {
              outline: none;
              border-color: #0078d4;
            }
          }

          .action-btn {
            padding: 0.4rem 0.75rem;
            border: 0.125rem solid;
            border-color: #ffffff #808080 #808080 #ffffff;
            background: #c0c0c0;
            font-size: 0.8rem;
            font-weight: bold;
            cursor: pointer;
            font-family: 'MS Sans Serif', sans-serif;

            &:hover:not(:disabled) {
              background: #e0e0e0;
            }

            &:active:not(:disabled) {
              border-color: #808080 #ffffff #ffffff #808080;
              background: #d0d0d0;
            }

            &:disabled {
              opacity: 0.5;
              cursor: not-allowed;
            }
          }
        }
      }
    }
  }

  .window-statusbar {
    background: #f0f0f0;
    padding: 0.25rem 0.5rem;
    border-top: 0.125rem solid #d4d4d4;
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 1.5rem;
    border: 0.125rem solid;
    border-color: #ffffff #808080 #808080 #ffffff;
    border-top-color: #808080;
    flex-shrink: 0;

    .status-info {
      display: flex;
      align-items: center;
      gap: 0.375rem;
      font-size: 0.75rem;
      color: #666;

      .status-icon {
        font-size: 0.875rem;
        color: #0078d4;
      }
    }
  }
}
</style>


