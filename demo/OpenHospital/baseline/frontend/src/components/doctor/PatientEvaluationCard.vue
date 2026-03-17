<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheck, CircleClose, QuestionFilled } from '@element-plus/icons-vue'
import { useDoctorStore } from '../../stores/doctor'

interface Examination {
  ordered_tick: number
  items: string[]
  expected_items: string[]
  precision: number
  has_ground_truth: boolean
}

interface PatientEvaluation {
  patient_id: string
  patient_name: string
  diagnosis: {
    predicted: string
    expected: string
    correct: boolean
    available: boolean
    correct_count?: number  // For comorbidity: number of correct diagnoses
    total_expected?: number // For comorbidity: total expected diagnoses
  }
  examinations: Examination[]
  examination_precision: number
  treatment: {
    provided: boolean
    diagnosis: string
    treatment_plan: string
    reference_treatment?: string  // 添加参考Treatment Plan
    evaluation?: any // 后端返回的评估结果
  }
}

interface Props {
  evaluation: PatientEvaluation
}

const props = defineProps<Props>()
const doctorStore = useDoctorStore()

const evaluationResult = computed(() => {
  if (props.evaluation.treatment.evaluation) {
    return props.evaluation.treatment.evaluation
  }
  if (!doctorStore.treatmentEvaluations || !props.evaluation?.patient_id) return null
  return doctorStore.treatmentEvaluations[props.evaluation.patient_id] || null
})
const performanceStatus = computed(() => {
  if (!evaluationResult.value) return null

  const diag = props.evaluation.diagnosis
  const totalExpected = diag.total_expected ?? 1
  const correctCount = diag.correct_count ?? (diag.correct ? 1 : 0)
  if (diag.available && correctCount === 0) {
    return 'failed'
  }
  if (diag.available && correctCount < totalExpected) {
    return evaluationResult.value.overall_score >= 0.5 ? 'partial' : 'failed'
  }
  return evaluationResult.value.overall_score >= 0.6 ? 'certified' : 'failed'
})

const diagnosisStatusConfig = computed(() => {
  const diag = props.evaluation.diagnosis
  if (!diag.predicted) {
    return { icon: QuestionFilled, color: '#909399', text: 'Not Diagnosed', subtext: '' }
  }
  if (!diag.available) {
    return { icon: QuestionFilled, color: '#909399', text: 'No Ground Truth', subtext: '' }
  }
  const totalExpected = diag.total_expected ?? 1
  const correctCount = diag.correct_count ?? (diag.correct ? 1 : 0)
  if (diag.correct || correctCount === totalExpected) {
    return { icon: CircleCheck, color: '#67c23a', text: 'Correct', subtext: totalExpected > 1 ? `${correctCount}/${totalExpected}` : '' }
  }
  if (correctCount > 0 && correctCount < totalExpected) {
    return { icon: QuestionFilled, color: '#e6a23c', text: 'Partial', subtext: `${correctCount}/${totalExpected}` }
  }
  return { icon: CircleClose, color: '#f56c6c', text: 'Incorrect', subtext: totalExpected > 1 ? `0/${totalExpected}` : '' }
})

const examinationScoreType = computed(() => {
  const precision = props.evaluation.examination_precision
  if (precision >= 0.8) return 'success'
  if (precision >= 0.5) return 'warning'
  return 'danger'
})

const treatmentScoreType = computed(() => {
  if (!evaluationResult.value) return ''
  const score = evaluationResult.value.overall_score
  if (score >= 0.8) return 'success'
  if (score >= 0.5) return 'warning'
  return 'danger'
})

const formatPercentage = (value: number) => {
  return (value * 100).toFixed(1) + '%'
}
</script>

<template>
  <div class="medical-transcript">
    <div class="transcript-header">
      <div class="transcript-title">CLINICAL PERFORMANCE TRANSCRIPT</div>
      <div class="transcript-subtitle">HOSPITAL ACADEMY OF SIMULATION</div>
    </div>

    <div class="transcript-body">
      <div class="info-grid">
        <div class="info-item">
          <label>PHYSICIAN-IN-CHARGE:</label>
          <span class="value underline">Doctor_AI</span>
        </div>
        <div class="info-item">
          <label>PATIENT SUBJECT:</label>
          <span class="value underline">{{ evaluation.patient_name }}</span>
        </div>
        <div class="info-item">
          <label>SUBJECT ID:</label>
          <span class="value underline">{{ evaluation.patient_id }}</span>
        </div>
        <div class="info-item">
          <label>EXAM DATE:</label>
          <span class="value underline">TICK {{ evaluation.examinations[0]?.ordered_tick || 'N/A' }}</span>
        </div>
      </div>

      <div class="divider-dashed"></div>
      <div class="grades-section">
        <h4 class="section-label">COURSE EVALUATIONS</h4>
        <div class="grade-row">
          <div class="subject">
            <span class="name">Clinical Diagnosis</span>
          </div>
          <div class="result">
            <span class="status-text" :class="diagnosisStatusConfig.text.toLowerCase().replace(' ', '-')">
              {{ diagnosisStatusConfig.text.toUpperCase() }}
              <span v-if="diagnosisStatusConfig.subtext" class="status-subtext">
                ({{ diagnosisStatusConfig.subtext }})
              </span>
            </span>
            <span v-if="props.evaluation.diagnosis.predicted && props.evaluation.diagnosis.available"
                  class="pixel-status-icon"
                  :class="diagnosisStatusConfig.text.toLowerCase()">
              {{ diagnosisStatusConfig.text === 'Correct' ? '✓' : diagnosisStatusConfig.text === 'Partial' ? '½' : '×' }}
            </span>
          </div>
        </div>
        <div class="diagnosis-detail">
          <div class="detail-line"><label>PREDICTED:</label> {{ evaluation.diagnosis.predicted || 'N/A' }}</div>
          <div v-if="evaluation.diagnosis.available" class="detail-line"><label>EXPECTED:</label> {{ evaluation.diagnosis.expected }}</div>
        </div>
        <div class="grade-row">
          <div class="subject">
            <span class="name">Examination Precision</span>
          </div>
          <div class="score-box" :class="examinationScoreType">
            {{ formatPercentage(evaluation.examination_precision) }}
          </div>
        </div>
        <div v-if="evaluation.examinations.length > 0" class="examination-details-container">
          <div class="details-header-mini">EXAMINATION ITEMS ({{ evaluation.examinations.length }})</div>
          <div v-for="(exam, index) in evaluation.examinations" :key="index" class="exam-group">
            <div class="exam-header">
              <span class="tick">TICK {{ exam.ordered_tick }}</span>
              <span class="exam-precision">PRECISION: {{ formatPercentage(exam.precision) }}</span>
            </div>
            
            <div class="exam-line">
              <label>ORDERED:</label>
              <div class="tag-container">
                <span 
                  v-for="item in exam.items" 
                  :key="item" 
                  class="item-tag"
                  :class="{ correct: exam.expected_items.includes(item) }"
                >
                  {{ item }}
                </span>
                <span v-if="exam.items.length === 0" class="none-text">None</span>
              </div>
            </div>
            
            <div v-if="exam.has_ground_truth" class="exam-line">
              <label>EXPECTED:</label>
              <div class="tag-container">
                <span 
                  v-for="item in exam.expected_items" 
                  :key="item" 
                  class="item-tag expected"
                >
                  {{ item }}
                </span>
                <span v-if="exam.expected_items.length === 0" class="none-text">None</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="evaluation.treatment.provided" class="treatment-grades">
          <div class="grade-row">
            <div class="subject">
              <span class="name">Therapeutic Planning</span>
            </div>
            <div v-if="evaluationResult" class="score-box" :class="treatmentScoreType">
              {{ (evaluationResult.overall_score * 100).toFixed(1) + '%' }}
            </div>
            <div v-else-if="evaluation.treatment.reference_treatment" class="pending-status">
              <span>Pending Evaluation (Auto after treatment completion)</span>
            </div>
          </div>
          <div class="treatment-plans-container">
            <div class="treatment-plan-box">
              <div class="plan-header doctor">
                <span class="plan-label">DOCTOR'S TREATMENT PLAN</span>
              </div>
              <div class="plan-content">
                {{ evaluation.treatment.treatment_plan || 'No treatment plan provided' }}
              </div>
            </div>
            <div v-if="evaluation.treatment.reference_treatment" class="treatment-plan-box">
              <div class="plan-header reference">
                <span class="plan-label">REFERENCE TREATMENT (GROUND TRUTH)</span>
              </div>
              <div class="plan-content">
                {{ evaluation.treatment.reference_treatment }}
              </div>
            </div>
          </div>

          <div v-if="evaluationResult" class="llm-grades">
            <div class="sub-grade">
              <label>SAFETY & CONTRAINDICATIONS:</label>
              <span class="val">{{ (evaluationResult.safety * 100).toFixed(0) }}%</span>
            </div>
            <div class="sub-grade">
              <label>EFFECTIVENESS & ALIGNMENT:</label>
              <span class="val">{{ (evaluationResult.effectiveness_alignment * 100).toFixed(0) }}%</span>
            </div>
            <div class="sub-grade">
              <label>PERSONALIZATION:</label>
              <span class="val">{{ (evaluationResult.personalization * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>
      </div>

      <div class="divider-dashed"></div>
      <div class="remarks-section">
        <h4 class="section-label">FACULTY COMMENTS</h4>
        <div class="comments-box">
          <template v-if="evaluationResult">
            {{ evaluationResult.reasoning }}
          </template>
          <template v-else>
            Waiting for full therapeutic evaluation...
          </template>
        </div>
      </div>
      <div class="transcript-footer">
        <div class="final-grade-box">
          <label>OVERALL PERFORMANCE</label>
          <div v-if="performanceStatus" class="pixel-rectangular-seal" :class="performanceStatus">
            <div class="seal-inner">
              <div class="seal-main">{{ performanceStatus.toUpperCase() }}</div>
            </div>
          </div>
          <div v-else class="grade-value">PENDING</div>
        </div>
        
        <div class="official-stamps">
          <div v-if="diagnosisStatusConfig.text === 'Correct'" class="stamp certified">CERTIFIED</div>
          <div v-if="diagnosisStatusConfig.text === 'Incorrect'" class="stamp failed">FAILED</div>
          <div class="stamp validated">VALIDATED</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.medical-transcript {
  background: #fff;
  border: 0.1875rem solid #333;
  padding: 1.5rem;
  box-shadow: 0.5rem 0.5rem 0 rgba(0,0,0,0.1);
  image-rendering: pixelated;
  font-family: 'Courier New', Courier, monospace;
  position: relative;
  overflow: visible;
  margin-bottom: 1.5rem;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 1.875rem;
    bottom: 0;
    width: 0.125rem;
    border-left: 0.0625rem solid #ffcccc;
    border-right: 0.0625rem solid #ffcccc;
    z-index: 1;
  }

  .transcript-header {
    text-align: center;
    border-bottom: 0.25rem double #333;
    padding-bottom: 1rem;
    margin-bottom: 1.5rem;
    position: relative;
    z-index: 2;

    .transcript-title {
      font-size: 1.25rem;
      font-weight: 900;
      letter-spacing: 0.125rem;
      color: #000;
    }

    .transcript-subtitle {
      font-size: 0.6875rem;
      font-weight: bold;
      color: #666;
      margin-top: 0.25rem;
    }
  }

  .transcript-body {
    position: relative;
    z-index: 2;
    padding-left: 1.25rem;
  }

  .info-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-bottom: 1.25rem;

    .info-item {
      display: flex;
      flex-direction: column;
      label {
        font-size: 0.625rem;
        color: #8b5a2b;
        font-weight: bold;
      }
      .value {
        font-size: 0.875rem;
        font-weight: bold;
        color: #333;
        &.underline {
          border-bottom: 0.0625rem solid #ccc;
          padding-bottom: 0.125rem;
        }
      }
    }
  }

  .divider-dashed {
    border-top: 0.125rem dashed #ccc;
    margin: 1.25rem 0;
  }

  .section-label {
    font-size: 0.75rem;
    font-weight: 900;
    color: #333;
    margin-bottom: 1rem;
    text-decoration: underline;
  }

  .grade-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
    background: #f8f9fa;
    padding: 0.5rem 0.75rem;
    border: 0.0625rem solid #eee;

    .subject {
      .name { font-weight: 900; font-size: 0.875rem; color: #000; }
    }

    .result {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      .status-text {
        font-weight: 900;
        font-size: 0.8125rem;
        &.correct { color: #27ae60; }
        &.incorrect { color: #d63031; }
        &.partial { color: #e67e22; }
        &.not-diagnosed { color: #909399; }
        &.no-ground-truth { color: #909399; }

        .status-subtext {
          font-size: 0.6875rem;
          font-weight: normal;
        }
      }

      .pixel-status-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.125rem;
        height: 1.125rem;
        font-family: 'Courier New', Courier, monospace;
        font-weight: 900;
        font-size: 1rem;
        border: 0.125rem solid;
        line-height: 1;
        image-rendering: pixelated;
        margin-left: 0.25rem;
        box-shadow: 0.125rem 0.125rem 0 rgba(0,0,0,0.1);

        &.correct {
          color: #27ae60;
          border-color: #27ae60;
          background: #eef9f5;
        }

        &.partial {
          color: #e67e22;
          border-color: #e67e22;
          background: #fff8ee;
        }

        &.incorrect {
          color: #d63031;
          border-color: #d63031;
          background: #fef0f0;
        }
      }
    }

    .score-box {
      font-family: 'Press Start 2P', cursive;
      font-size: 0.75rem;
      padding: 0.25rem 0.5rem;
      border: 0.125rem solid #333;
      &.success { background: #eef9f5; color: #27ae60; }
      &.warning { background: #fff8ee; color: #e67e22; }
      &.danger { background: #fef0f0; color: #d63031; }
    }
  }

  .diagnosis-detail {
    padding: 0 0.75rem 1rem;
    font-size: 0.75rem;
    color: #666;
    .detail-line {
      margin-bottom: 0.25rem;
      label { font-weight: bold; color: #999; width: 5rem; display: inline-block; }
    }
  }

  .examination-details-container {
    padding: 0 0.75rem 1rem;
    font-family: monospace;

    .details-header-mini {
      font-size: 0.6875rem;
      font-weight: 900;
      color: #333;
      margin-bottom: 0.75rem;
      text-transform: uppercase;
      border-left: 0.1875rem solid #ffcc00;
      padding-left: 0.5rem;
    }

    .exam-group {
      margin-bottom: 1rem;
      border: 0.0625rem dashed #ccc;
      padding: 0.625rem;
      background: #fff;

      .exam-header {
        display: flex;
        justify-content: space-between;
        font-size: 0.625rem;
        color: #999;
        margin-bottom: 0.625rem;
        border-bottom: 0.0625rem solid #eee;
        padding-bottom: 0.25rem;
        font-weight: bold;
      }

      .exam-line {
        display: flex;
        margin-bottom: 0.5rem;
        align-items: flex-start;
        gap: 0.75rem;

        label {
          font-size: 0.625rem;
          font-weight: bold;
          color: #8b5a2b;
          min-width: 5rem;
          flex-shrink: 0;
          margin-top: 0.25rem;
          margin-right: 0.5rem;
        }

        .tag-container {
          display: flex;
          flex-wrap: wrap;
          gap: 0.375rem;

          .item-tag {
            font-size: 0.625rem;
            padding: 0.125rem 0.5rem;
            background: #f4f4f4;
            border: 0.0625rem solid #ddd;
            color: #777;
            border-radius: 0.125rem;

            &.correct {
              background: #f0fdf4;
              border-color: #2ecc71;
              color: #166534;
            }

            &.expected {
              background: #f0fdf4;
              border-color: #2ecc71;
              color: #166534;
            }
          }

          .none-text {
            font-size: 0.625rem;
            color: #ccc;
            font-style: italic;
          }
        }
      }
    }

    .average-precision-line {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.6875rem;
      font-weight: bold;
      margin-top: 0.75rem;

      label {
        color: #333;
      }

      .value {
        background: #fff8ee;
        color: #e67e22;
        padding: 0.125rem 0.375rem;
        border: 0.0625rem solid #e6a23c;
      }
    }
  }

  .pixel-rectangular-seal {
    position: absolute;
    right: 0;
    top: -0.9375rem;
    z-index: 10;
    pointer-events: none;
    transform: rotate(-5deg);
    padding: 0.1875rem;
    border: 0.1875rem solid currentColor !important;
    background: transparent;
    display: inline-block;
    opacity: 0.95;

    &.certified {
      color: #2ecc71;
    }

    &.partial {
      color: #e67e22;
    }

    &.failed {
      color: #ff4b4b;
    }

    .seal-inner {
      border: 0.09375rem solid currentColor !important;
      padding: 0.5rem 1.25rem;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }

    .seal-main {
      font-family: 'Press Start 2P', cursive !important;
      font-size: 1.5rem !important;
      font-weight: 900 !important;
      color: currentColor !important;
      margin: 0;
      padding: 0;
      white-space: nowrap;
      text-shadow: 0.125rem 0.125rem 0 rgba(0,0,0,0.1);
      line-height: 1.2;
    }
  }

  .llm-grades {
    padding: 0.75rem;
    border: 0.0625rem solid #ddd;
    border-top: none;
    margin-bottom: 1rem;
    background: #fff;

    .sub-grade {
      display: flex;
      align-items: baseline;
      margin-bottom: 0.375rem;
      font-size: 0.6875rem;

      label {
        color: #7f8c8d;
        flex: 1;
        display: flex;
        align-items: baseline;

        &::after {
          content: "";
          flex: 1;
          margin: 0 0.5rem;
          border-bottom: 0.125rem dotted #ddd;
        }
      }

      .val {
        font-weight: bold;
        color: #333;
        flex-shrink: 0;
      }
    }
  }

  .treatment-plans-container {
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    background: #f8f9fa;
    border: 0.0625rem solid #eee;
    border-top: none;
    margin-bottom: 0.75rem;

    .treatment-plan-box {
      border: 0.125rem solid #ddd;
      background: #fff;

      .plan-header {
        padding: 0.375rem 0.75rem;
        font-size: 0.625rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 0.03125rem;

        &.doctor {
          background: #e3f2fd;
          color: #1565c0;
          border-bottom: 0.125rem solid #1565c0;
        }

        &.reference {
          background: #f0fdf4;
          color: #166534;
          border-bottom: 0.125rem solid #166534;
        }
      }

      .plan-content {
        padding: 0.75rem;
        font-size: 0.75rem;
        line-height: 1.6;
        color: #333;
        white-space: pre-wrap;
        word-break: break-word;
        overflow: visible;
        text-overflow: unset;
        -webkit-line-clamp: unset;
        display: block;
      }
    }
  }

  .comments-box {
    background: #fffef5;
    border: 0.125rem solid #ddd;
    padding: 1rem;
    font-size: 0.8125rem;
    line-height: 1.6;
    color: #444;
    font-style: italic;
    min-height: 3.75rem;
  }

    .transcript-footer {
      margin-top: 2rem;
      display: flex;
      justify-content: flex-end;
      align-items: flex-end;

      .final-grade-box {
        position: relative;
        min-height: 6.25rem;
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        justify-content: center;
        padding-right: 1.25rem;

        label { font-size: 0.625rem; font-weight: bold; color: #666; }
      .grade-value {
        font-family: 'Press Start 2P', cursive;
        font-size: 1.5rem;
        margin-top: 0.5rem;
      }
    }

    .official-stamps {
      display: none;
    }
  }

  .pixel-btn {
    border-radius: 0;
    border: 0.125rem solid #333;
    font-family: monospace;
    font-weight: bold;
    box-shadow: 0.1875rem 0.1875rem 0 #ccc;
    background: #409eff;
    color: #fff;
    &:active { transform: translate(0.125rem, 0.125rem); box-shadow: 0.0625rem 0.0625rem 0 #ccc; }
  }

  .evaluating-status {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.75rem;
    color: #e6a23c;
    font-weight: bold;
  }

  .pending-status {
    font-size: 0.75rem;
    color: #909399;
    font-style: italic;
  }
}
</style>
