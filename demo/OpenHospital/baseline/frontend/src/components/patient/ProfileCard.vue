<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Patient } from '@/types'

interface Props {
  patient: Patient & {
    present_illness_history?: {
      chief_complaint?: string
      triggers_of_disease?: string
      symptoms_and_progression?: string
      current_general_status?: {
        diet?: string
        sleep?: string
        excretion?: string
        weight_change?: string
      }
    }
    medical_history?: {
      previous_diseases?: string[]
      long_term_medication?: string
      surgery_or_trauma?: string
      allergies?: {
        food?: string[]
        drug?: string[]
      }
      infectious_diseases?: string[]
      blood_transfusion?: string
      vaccinations?: string
    }
    personal_history?: {
      smoking?: string
      alcohol?: string
      obstetric_history?: string
      menstrual_history?: string
    }
    family_history?: {
      similar_illness?: string
      hereditary_diseases?: string
    }
  }
}

const props = defineProps<Props>()
const clickCount = ref(0)
const isPhotoFallen = ref(false)
const avatarUrl = computed(() => {
  const genderPrefix = props.patient.demographics.gender === 'Male' ? 'm' : 'f'
  return `https://api.dicebear.com/7.x/pixel-art/svg?seed=${genderPrefix}_${props.patient.id}&backgroundColor=b6e3f4,c0aede,d1d4f9`
})
const chiefComplaint = computed(() => {
  return props.patient.present_illness_history?.chief_complaint || props.patient.initial_complaint || 'N/A'
})
const symptomsDescription = computed(() => {
  const symptoms = props.patient.present_illness_history?.symptoms_and_progression
  if (symptoms) {
    return symptoms.length > 300 ? symptoms.substring(0, 300) + '...' : symptoms
  }
  return 'No detailed symptoms recorded.'
})
const dietStatus = computed(() => {
  return props.patient.present_illness_history?.current_general_status?.diet || 'N/A'
})

const sleepStatus = computed(() => {
  return props.patient.present_illness_history?.current_general_status?.sleep || 'N/A'
})

const excretionStatus = computed(() => {
  return props.patient.present_illness_history?.current_general_status?.excretion || 'N/A'
})

const weightChangeStatus = computed(() => {
  return props.patient.present_illness_history?.current_general_status?.weight_change || 'N/A'
})
const allergyFood = computed(() => {
  const foods = props.patient.medical_history?.allergies?.food
  return foods && foods.length > 0 && foods[0] !== 'None' ? foods.join(', ') : 'None'
})

const allergyDrug = computed(() => {
  const drugs = props.patient.medical_history?.allergies?.drug
  return drugs && drugs.length > 0 && drugs[0] !== 'None' ? drugs.join(', ') : 'None'
})
const previousDiseases = computed(() => {
  const diseases = props.patient.medical_history?.previous_diseases
  return diseases && diseases.length > 0 ? diseases.join('; ') : 'None'
})
const medications = computed(() => {
  const meds = props.patient.medical_history?.long_term_medication
  return meds || 'None'
})
const surgeryTrauma = computed(() => {
  const surgery = props.patient.medical_history?.surgery_or_trauma
  return surgery || 'None'
})
const infectiousDiseases = computed(() => {
  const diseases = props.patient.medical_history?.infectious_diseases
  return diseases && diseases.length > 0 ? diseases.join('; ') : 'None'
})
const bloodTransfusion = computed(() => {
  const transfusion = props.patient.medical_history?.blood_transfusion
  return transfusion || 'None'
})
const vaccinations = computed(() => {
  const vax = props.patient.medical_history?.vaccinations
  return vax || 'None'
})
const smokingHistory = computed(() => {
  const smoking = props.patient.personal_history?.smoking
  return smoking || 'None'
})
const alcoholHistory = computed(() => {
  const alcohol = props.patient.personal_history?.alcohol
  return alcohol || 'None'
})
const familySimilarIllness = computed(() => {
  return props.patient.family_history?.similar_illness || 'None'
})

const familyHereditaryDiseases = computed(() => {
  return props.patient.family_history?.hereditary_diseases || 'None'
})
const obstetricHistory = computed(() => {
  return props.patient.personal_history?.obstetric_history || 'None'
})

const menstrualHistory = computed(() => {
  return props.patient.personal_history?.menstrual_history || 'None'
})
function handlePhotoClick() {
  if (isPhotoFallen.value) return

  clickCount.value++
  if (clickCount.value >= 5) {
    isPhotoFallen.value = true
  }
}
</script>

<template>
  <div class="medical-chart">
    <div class="chart-header">
      <div class="clip"></div>
      <div class="chart-title">PATIENT MEDICAL RECORD</div>
      <div class="confidential-stamp">CONFIDENTIAL</div>
    </div>

    <div class="chart-paper">
      <div class="paper-section top-row">
        <div class="patient-photo-wrapper">
          <div class="patient-photo" :class="{ 'fallen': isPhotoFallen }" @click="handlePhotoClick">
            <div class="nail"></div>
            <div class="photo-inner">
              <img :src="avatarUrl" :alt="props.patient.name" class="pixel-avatar" />
            </div>
          </div>
          <div class="wooden-board" :class="{ 'revealed': isPhotoFallen }">
            <div class="board-text">Happy DALAB</div>
          </div>
        </div>
        
        <div class="patient-id-card">
          <div class="field">
            <label>NAME:</label>
            <span class="value name-value">{{ props.patient.name }}</span>
          </div>
          <div class="meta-row">
            <div class="field">
              <label>AGE:</label>
              <span class="value">{{ props.patient.demographics.age }}</span>
            </div>
            <div class="field">
              <label>SEX:</label>
              <span class="value">{{ props.patient.demographics.gender === 'Male' ? 'M' : 'F' }}</span>
            </div>
            <div class="field">
              <label>ID:</label>
              <span class="value id-value">{{ props.patient.id }}</span>
            </div>
          </div>
          <div class="field" v-if="props.patient.demographics.marital_status">
            <label>MARITAL STATUS:</label>
            <span class="value">{{ props.patient.demographics.marital_status }}</span>
          </div>
          <div class="field" v-if="props.patient.demographics.occupation">
            <label>OCCUPATION:</label>
            <span class="value occupation-value">{{ props.patient.demographics.occupation }}</span>
          </div>
        </div>
      </div>
      <div class="paper-body">
        <div class="medical-section highlight-section">
          <div class="section-label large-label">
            <el-icon><View /></el-icon> PERSONA
          </div>
          <div class="section-content persona-content">
            {{ props.patient.persona }}
          </div>
        </div>

        <div class="history-grid">
          <div class="history-block">
            <div class="block-title">PRESENT ILLNESS HISTORY</div>
            <div class="block-body">
              <div class="sub-field">
                <div class="sub-label">CHIEF COMPLAINT</div>
                <div class="sub-content">{{ chiefComplaint }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">SYMPTOMS & PROGRESSION</div>
                <div class="sub-content">{{ symptomsDescription }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">CURRENT GENERAL STATUS</div>
                <div class="nested-content">
                  <div class="nested-item">
                    <span class="nested-label">DIET:</span> {{ dietStatus }}
                  </div>
                  <div class="nested-item">
                    <span class="nested-label">SLEEP:</span> {{ sleepStatus }}
                  </div>
                  <div class="nested-item">
                    <span class="nested-label">EXCRETION:</span> {{ excretionStatus }}
                  </div>
                  <div class="nested-item">
                    <span class="nested-label">WEIGHT CHANGE:</span> {{ weightChangeStatus }}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="history-block">
            <div class="block-title">MEDICAL HISTORY</div>
            <div class="block-body">
              <div class="sub-field">
                <div class="sub-label">PREVIOUS DISEASES</div>
                <div class="sub-content">{{ previousDiseases }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">LONG TERM MEDICATION</div>
                <div class="sub-content">{{ medications }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">SURGERY OR TRAUMA</div>
                <div class="sub-content">{{ surgeryTrauma }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">INFECTIOUS DISEASES</div>
                <div class="sub-content">{{ infectiousDiseases }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">BLOOD TRANSFUSION</div>
                <div class="sub-content">{{ bloodTransfusion }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">VACCINATIONS</div>
                <div class="sub-content">{{ vaccinations }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">ALLERGIES</div>
                <div class="nested-content">
                  <div class="nested-item">
                    <span class="nested-label">FOOD:</span> {{ allergyFood }}
                  </div>
                  <div class="nested-item">
                    <span class="nested-label">DRUG:</span> {{ allergyDrug }}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="history-block">
            <div class="block-title">PERSONAL HISTORY</div>
            <div class="block-body">
              <div class="sub-field">
                <div class="sub-label">SMOKING</div>
                <div class="sub-content">{{ smokingHistory }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">ALCOHOL</div>
                <div class="sub-content">{{ alcoholHistory }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">OBSTETRIC HISTORY</div>
                <div class="sub-content">{{ obstetricHistory }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">MENSTRUAL HISTORY</div>
                <div class="sub-content">{{ menstrualHistory }}</div>
              </div>
            </div>
          </div>
          <div class="history-block">
            <div class="block-title">FAMILY HISTORY</div>
            <div class="block-body">
              <div class="sub-field">
                <div class="sub-label">SIMILAR ILLNESS</div>
                <div class="sub-content">{{ familySimilarIllness }}</div>
              </div>
              <div class="sub-field">
                <div class="sub-label">HEREDITARY DISEASES</div>
                <div class="sub-content">{{ familyHereditaryDiseases }}</div>
              </div>
            </div>
          </div>
        </div>

      </div>
      <div class="chart-footer">
        <div class="medical-seal">
          <div class="seal-inner">HOSPITAL SYST.</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.medical-chart {
  position: relative;
  background: #dcb06e; // Folder color
  padding: 0.625rem;
  border: 0.25rem solid #8b5a2b;
  box-shadow: 0.5rem 0.5rem 0rem rgba(0, 0, 0, 0.2);
  image-rendering: pixelated;

  .chart-header {
    height: 2.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    margin-bottom: 0.3125rem;

    .clip {
      width: 5rem;
      height: 1.25rem;
      background: #a0a0a0;
      border: 0.1875rem solid #606060;
      position: absolute;
      top: -0.9375rem;
      z-index: 10;
      box-shadow: inset 0.125rem 0.125rem 0 #c0c0c0;
    }

    .chart-title {
      font-family: 'Courier New', Courier, monospace;
      font-weight: bold;
      font-size: 0.875rem;
      color: #5d3a1a;
      letter-spacing: 0.125rem;
    }

    .confidential-stamp {
      position: absolute;
      right: 0.625rem;
      top: 0;
      border: 0.125rem solid #ff4b4b;
      color: #ff4b4b;
      padding: 0.125rem 0.375rem;
      font-size: 0.625rem;
      font-weight: bold;
      transform: rotate(5deg);
      opacity: 0.8;
    }
  }

  .chart-paper {
    background: #fdf6e3; // Paper color
    border: 0.1875rem solid #333;
    padding: 1.5rem;
    min-height: 25rem;
    position: relative;
    box-shadow: inset 0.25rem 0.25rem 0 rgba(255, 255, 255, 0.5);
    background-image: linear-gradient(#eee 0.0625rem, transparent 0.0625rem);
    background-size: 100% 1.75rem;

    .paper-section {
      margin-bottom: 1.25rem;
    }

    .top-row {
      display: flex;
      gap: 1.5rem;
      align-items: flex-start;
      border-bottom: 0.1875rem double #333;
      padding-bottom: 1.25rem;
      margin-bottom: 1.5rem;
    }

    .patient-photo-wrapper {
      position: relative;
      width: 7.5rem;
      height: 7.5rem;
    }

    .patient-photo {
      position: relative;
      width: 7.5rem;
      height: 7.5rem;
      background: #fff;
      padding: 0.375rem;
      border: 0.1875rem solid #333;
      transform-origin: center 0.125rem;
      animation: photo-wobble 4s ease-in-out infinite;
      cursor: pointer;
      z-index: 2;
      transition: transform 0.2s ease;

      &:hover:not(.fallen) {
        transform: scale(1.05);
      }

      &.fallen {
        animation: photo-fall 1.2s ease-in forwards;
        cursor: default;
        pointer-events: none;
      }

      .photo-inner {
        width: 100%;
        height: 100%;
        background: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;

        .pixel-avatar {
          width: 100%;
          height: 100%;
          image-rendering: pixelated;
          object-fit: cover;
        }
      }

      .nail {
        position: absolute;
        top: -0.5rem;
        left: 50%;
        transform: translateX(-50%);
        width: 1rem;
        height: 1rem;
        background: #7f8c8d;
        border: 0.125rem solid #2c3e50;
        border-radius: 50%;
        z-index: 5;
        box-shadow: 0.125rem 0.125rem 0 rgba(0,0,0,0.2);

        &::after {
          content: '';
          position: absolute;
          top: 0.1875rem;
          left: 0.1875rem;
          width: 0.25rem;
          height: 0.25rem;
          background: #ecf0f1;
        }
      }
    }

    .wooden-board {
      position: absolute;
      top: 0;
      left: 0;
      width: 7.5rem;
      height: 7.5rem;
      background: #8b6914; // 木板颜色
      border: 0.1875rem solid #5d4a0f;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transform: scale(0.8);
      transition: opacity 0.5s ease, transform 0.5s ease;
      z-index: 1;
      background-image:
        repeating-linear-gradient(
          90deg,
          transparent,
          transparent 0.125rem,
          rgba(0, 0, 0, 0.1) 0.125rem,
          rgba(0, 0, 0, 0.1) 0.25rem
        ),
        repeating-linear-gradient(
          0deg,
          transparent,
          transparent 0.125rem,
          rgba(0, 0, 0, 0.05) 0.125rem,
          rgba(0, 0, 0, 0.05) 0.25rem
        );

      &.revealed {
        opacity: 1;
        transform: scale(1);
      }

      .board-text {
        font-family: 'Courier New', Courier, monospace;
        font-weight: 900;
        font-size: 0.875rem;
        color: #ffd700; // 金色文字
        text-shadow:
          0.125rem 0.125rem 0 #000,
          -0.0625rem -0.0625rem 0 rgba(255, 255, 255, 0.3);
        letter-spacing: 0.125rem;
        text-align: center;
        line-height: 1.2;
        transform: rotate(-5deg);
        animation: text-glow 2s ease-in-out infinite alternate;
      }
    }

    @keyframes photo-wobble {
      0%, 100% { transform: rotate(-2deg); }
      50% { transform: rotate(3deg); }
    }

    @keyframes photo-fall {
      0% {
        transform: rotate(0deg) translateY(0);
        opacity: 1;
      }
      50% {
        transform: rotate(45deg) translateY(3.125rem);
        opacity: 0.8;
      }
      100% {
        transform: rotate(90deg) translateY(12.5rem);
        opacity: 0;
      }
    }

    @keyframes text-glow {
      0% {
        text-shadow:
          0.125rem 0.125rem 0 #000,
          -0.0625rem -0.0625rem 0 rgba(255, 255, 255, 0.3),
          0 0 0.3125rem rgba(255, 215, 0, 0.5);
      }
      100% {
        text-shadow:
          0.125rem 0.125rem 0 #000,
          -0.0625rem -0.0625rem 0 rgba(255, 255, 255, 0.3),
          0 0 0.9375rem rgba(255, 215, 0, 0.8);
      }
    }

    .patient-id-card {
      flex: 1;
      font-family: 'Courier New', Courier, monospace;

      .field {
        display: flex;
        align-items: baseline;
        gap: 0.5rem;
        margin-bottom: 0.5rem;

        label {
          font-weight: bold;
          color: #666;
          font-size: 0.75rem;
        }

        .value {
          color: #222;
          font-size: 1rem;
          border-bottom: 0.0625rem solid #333;
          flex: 1;
        }

        .name-value {
          font-size: 1.25rem;
          font-weight: bold;
        }

        .id-value {
          font-size: 0.75rem;
          color: #555;
        }

        .occupation-value {
          font-size: 0.8125rem;
          color: #444;
        }
      }

      .meta-row {
        display: flex;
        gap: 1.25rem;
      }
    }

    .paper-body {
      padding-top: 0.625rem;
      font-family: 'Courier New', Courier, monospace;
      color: #333;
    }
    .highlight-section {
      background: rgba(220, 176, 110, 0.1);
      border: 0.125rem solid rgba(139, 90, 43, 0.2);
      border-radius: 0.5rem;
      padding: 0.9375rem;
      margin-bottom: 1.5625rem;
      box-shadow: inset 0.125rem 0.125rem 0.3125rem rgba(0,0,0,0.05);

      .large-label {
        font-size: 1rem !important;
        padding: 0.25rem 0.75rem !important;
        margin-bottom: 0.625rem !important;
        background: #8b5a2b !important;
        color: #fff !important;
      }

      .persona-content {
        font-size: 0.9375rem;
        line-height: 1.7;
        font-style: italic;
        color: #4a3728;
      }
    }
    .history-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.25rem;
    }

    .history-block {
      background: rgba(255, 255, 255, 0.4);
      border: 0.0625rem solid #ccc;
      border-radius: 0.375rem;
      overflow: hidden;
      display: flex;
      flex-direction: column;

      .block-title {
        background: rgba(139, 90, 43, 0.15);
        padding: 0.5rem 0.75rem;
        font-weight: bold;
        font-size: 0.8125rem;
        color: #5d3a1a;
        border-bottom: 0.0625rem solid #ccc;
        text-transform: uppercase;
        letter-spacing: 0.0625rem;
      }

      .block-body {
        padding: 0.75rem;
        flex: 1;
      }
    }
    .sub-field {
      margin-bottom: 0.9375rem;

      &:last-child {
        margin-bottom: 0;
      }

      .sub-label {
        font-size: 0.6875rem;
        font-weight: bold;
        color: #7f8c8d;
        margin-bottom: 0.1875rem;
        text-transform: uppercase;
      }

      .sub-content {
        font-size: 0.8125rem;
        line-height: 1.5;
        color: #2c3e50;
        white-space: pre-wrap;
      }
    }
    .nested-content {
      padding-left: 0.75rem;
      border-left: 0.125rem solid rgba(139, 90, 43, 0.15);
      margin-top: 0.3125rem;

      .nested-item {
        margin-bottom: 0.5rem;
        font-size: 0.8125rem;
        line-height: 1.4;
        color: #2c3e50;

        &:last-child {
          margin-bottom: 0;
        }

        .nested-label {
          font-size: 0.625rem;
          font-weight: bold;
          color: #a0522d; // Sienna color for distinction
          margin-right: 0.25rem;
        }
      }
    }

    .section-label {
      font-weight: bold;
      color: #5d3a1a;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.375rem;
      font-size: 0.8125rem;
      text-transform: uppercase;
      background: rgba(220, 176, 110, 0.2);
      padding: 0.125rem 0.5rem;
      border-radius: 0.25rem;
      width: fit-content;
      border: 0.0625rem solid rgba(139, 90, 43, 0.3);
    }

    .chart-footer {
      margin-top: 1.875rem;
      display: flex;
      justify-content: flex-end;

      .medical-seal {
        width: 5rem;
        height: 5rem;
        border: 0.125rem dashed rgba(255, 75, 75, 0.4);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        transform: rotate(-15deg);

        .seal-inner {
          font-size: 0.625rem;
          font-weight: bold;
          color: rgba(255, 75, 75, 0.4);
          text-align: center;
        }
      }
    }
  } // End .chart-paper
} // End .medical-chart

@media (max-width: 56.25rem) {
  .history-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 48rem) {
  .medical-chart {
    .chart-header {
      padding: 0.375rem 0.75rem;

      .chart-title {
        font-size: 0.625rem !important;
      }

      .confidential-stamp {
        font-size: 0.5rem !important;
        padding: 0.125rem 0.375rem;
      }
    }

    .chart-paper {
      padding: 0.75rem;

      .paper-section.top-row {
        flex-direction: column;
        gap: 0.75rem;

        .patient-photo-wrapper {
          align-self: center;

          .patient-photo {
            width: 4rem;
            height: 5rem;
          }
        }
      }

      .paper-section {
        h3 {
          font-size: 0.6875rem;
        }

        .field-value {
          font-size: 0.6875rem;
        }

        .section-label {
          font-size: 0.6875rem;
        }

        .nested-content {
          .nested-item {
            font-size: 0.6875rem;

            .nested-label {
              font-size: 0.5625rem;
            }
          }
        }
      }

      .chart-footer {
        .medical-seal {
          width: 3.5rem;
          height: 3.5rem;

          .seal-inner {
            font-size: 0.5rem;
          }
        }
      }
    }
  }
}

@media (max-width: 30rem) {
  .medical-chart {
    .chart-paper {
      padding: 0.5rem;

      .paper-section {
        margin-bottom: 0.75rem;

        h3 {
          font-size: 0.625rem;
          margin-bottom: 0.25rem;
        }

        .field-value {
          font-size: 0.625rem;
        }

        .section-label {
          font-size: 0.625rem;
          padding: 0.0625rem 0.375rem;
        }

        .nested-content {
          padding-left: 0.5rem;

          .nested-item {
            font-size: 0.625rem;
            margin-bottom: 0.375rem;
          }
        }
      }
    }
  }
}
</style>
