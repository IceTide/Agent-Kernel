<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Histogram, TrendCharts, CircleCheck, Suitcase } from '@element-plus/icons-vue'
import type { PrescriptionRecord } from '@/types'

interface Props {
  prescription: PrescriptionRecord
  patientId?: string
  referenceTreatment?: string
}

const props = defineProps<Props>()

const statusConfig = {
  pending: { text: 'Pending', type: 'warning' as const },
  completed: { text: 'Completed', type: 'success' as const },
}

const status = computed(() => statusConfig[props.prescription.status])

const treatmentResultClass = computed(() => {
  if (!props.prescription.treatment_result) return ''
  return props.prescription.treatment_result.success ? 'success' : 'warning'
})
const isEvaluating = ref(false)
const evaluationResult = ref<any>(null)

async function evaluateTreatment() {
  if (!props.patientId || !props.referenceTreatment) {
    ElMessage.warning('缺少必要的评估数据（PatientID或参考Treatment Plan）')
    console.log('Debug - patientId:', props.patientId, 'referenceTreatment:', props.referenceTreatment)
    return
  }
  
  isEvaluating.value = true
  evaluationResult.value = null
  
  try {
    const response = await fetch('/api/doctors/evaluate-treatment', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        patient_id: props.patientId,
        diagnosis: props.prescription.diagnosis,
        treatment_plan: props.prescription.treatment_plan,
        reference_treatment: props.referenceTreatment
      })
    })
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `评估Failed: ${response.statusText}`)
    }
    
    const result = await response.json()
    evaluationResult.value = result
    ElMessage.success('Treatment Plan Evaluation Completed')
  } catch (error: any) {
    console.error('Treatment evaluation error:', error)
    ElMessage.error(error.message || 'Evaluation Failed, Please Try Again Later')
  } finally {
    isEvaluating.value = false
  }
}

const evaluationScoreColor = computed(() => {
  if (!evaluationResult.value) return ''
  const score = evaluationResult.value.overall_score
  if (score >= 0.8) return '#67c23a'
  if (score >= 0.5) return '#e6a23c'
  return '#f56c6c'
})
</script>

<template>
  <div class="treatment-card">
    <div class="card-header">
      <div class="header-info">
        <el-icon class="treatment-icon"><Suitcase /></el-icon>
        <span class="doctor-id">{{ props.prescription.doctor_id }}</span>
        <span class="tick">Tick {{ props.prescription.prescribed_tick }}</span>
      </div>
      <el-tag :type="status.type" size="small">{{ status.text }}</el-tag>
    </div>
    
    <div class="card-body">
      <div class="medical-certificate">
        <div class="certificate-header">
          <h3 class="certificate-title">MEDICAL DIAGNOSIS & TREATMENT</h3>
          <div class="certificate-number">No. {{ props.prescription.id }}</div>
        </div>
        
        <div class="certificate-content">
          <div class="certificate-field">
            <span class="field-label">Diagnosis:</span>
            <p class="diagnosis-text">{{ props.prescription.diagnosis }}</p>
          </div>
          
          <div class="certificate-field">
            <span class="field-label">Treatment Plan:</span>
            <p class="treatment-text">{{ props.prescription.treatment_plan }}</p>
          </div>
          
          <div class="certificate-field">
            <span class="field-label">Prescribed Date:</span>
            <span class="field-value">Tick {{ props.prescription.prescribed_tick }}</span>
          </div>
        </div>
        
        <div class="certificate-footer">
          <div class="signature-section">
            <div class="doctor-signature">
              <div class="signature-label">Physician:</div>
              <div class="signature-name">{{ props.prescription.doctor_id }}</div>
            </div>
            <div class="hospital-stamp">
              <div class="stamp-circle">
                <div class="stamp-text">
                  <div class="stamp-line1">HOSPITAL</div>
                  <div class="stamp-line2">SIMULATION</div>
                  <div class="stamp-star">★</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-if="props.patientId && props.referenceTreatment" class="evaluation-actions">
          <el-button 
            size="small" 
            type="primary" 
            :loading="isEvaluating"
            @click="evaluateTreatment"
          >
            <el-icon><Histogram /></el-icon>
            {{ isEvaluating ? 'Evaluating...' : 'LLM Evaluation' }}
          </el-button>
        </div>
      </div>
    <div v-if="evaluationResult" class="section evaluation-section">
      <h5>
        <el-icon><TrendCharts /></el-icon>
        LLM Evaluation Result
      </h5>
      <div class="evaluation-box">
        <div class="evaluation-score" :style="{ color: evaluationScoreColor }">
          <span class="score-label">Overall Score:</span>
          <span class="score-value">{{ (evaluationResult.overall_score * 100).toFixed(1) }}%</span>
        </div>
        
        <div class="evaluation-subscores">
          <div class="subscore-item">
            <span class="subscore-label">Clinical Appropriateness:</span>
            <el-progress 
              :percentage="evaluationResult.clinical_appropriateness * 100" 
              :color="evaluationScoreColor"
              :stroke-width="8"
            />
          </div>
          <div class="subscore-item">
            <span class="subscore-label">Completeness:</span>
            <el-progress 
              :percentage="evaluationResult.completeness * 100" 
              :color="evaluationScoreColor"
              :stroke-width="8"
            />
          </div>
          <div class="subscore-item">
            <span class="subscore-label">Safety:</span>
            <el-progress 
              :percentage="evaluationResult.safety * 100" 
              :color="evaluationScoreColor"
              :stroke-width="8"
            />
          </div>
        </div>
        
        <div class="evaluation-reasoning">
          <strong>Evaluation Reasoning:</strong>
          <p>{{ evaluationResult.reasoning }}</p>
        </div>
      </div>
    </div>
    
    <div v-if="props.prescription.treatment_result" class="section result-section">
      <h5>
        <el-icon><CircleCheck /></el-icon>
        Treatment Result
      </h5>
      <div class="result-box" :class="treatmentResultClass">
        <div class="result-header">
          <span class="result-label">
            {{ props.prescription.treatment_result.success ? '✅ Treatment Success' : '⚠️ Improvement Needed' }}
          </span>
          <span class="result-score">
            Score: {{ (props.prescription.treatment_result.score * 100).toFixed(1) }}%
          </span>
        </div>
        <p class="result-feedback">{{ props.prescription.treatment_result.feedback }}</p>
      </div>
    </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.treatment-card {
  background: #fff;
  border: 0.1875rem solid #333;
  box-shadow: 0.25rem 0.25rem 0 rgba(0, 0, 0, 0.1);
  margin-bottom: 1rem;
  image-rendering: pixelated;

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    background: #f8f9fa;
    border-bottom: 0.1875rem solid #333;

    .header-info {
      display: flex;
      align-items: center;
      gap: 0.625rem;

      .treatment-icon {
        color: #409eff;
        font-size: 1.125rem;
      }

      .doctor-id {
        font-family: monospace;
        font-weight: bold;
        font-size: 0.8125rem;
      }

      .tick {
        font-family: monospace;
        font-size: 0.75rem;
        color: #666;
        background: #eee;
        padding: 0.125rem 0.375rem;
        border: 0.0625rem solid #ccc;
      }
    }

    :deep(.el-tag) {
      font-family: monospace;
      font-weight: bold;
      text-transform: uppercase;
    }
  }

  .card-body {
    padding: 1.25rem;

    .medical-certificate {
      background: #fdf6e3; // Retro paper color
      border: 0.1875rem solid #333;
      padding: 1.5rem;
      position: relative;
      box-shadow: inset 0.25rem 0.25rem 0 rgba(255, 255, 255, 0.5), 0.375rem 0.375rem 0 rgba(0, 0, 0, 0.1);
      background-image: linear-gradient(#eee 0.0625rem, transparent 0.0625rem);
      background-size: 100% 1.625rem;

      &::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0.9375rem;
        bottom: 0;
        width: 0.125rem;
        border-left: 0.0625rem solid #ffcccc;
        border-right: 0.0625rem solid #ffcccc;
      }

      .certificate-header {
        text-align: center;
        border-bottom: 0.1875rem double #333;
        padding-bottom: 0.75rem;
        margin-bottom: 1.25rem;

        .certificate-title {
          margin: 0;
          font-family: 'Courier New', Courier, monospace;
          font-weight: 900;
          font-size: 1.25rem;
          color: #333;
          letter-spacing: 0.125rem;
          text-transform: uppercase;
        }

        .certificate-number {
          margin-top: 0.625rem;
          font-family: monospace;
          font-size: 0.6875rem;
          color: #666;
        }
      }

      .certificate-content {
        margin-bottom: 1.5rem;
        padding-left: 1.25rem;

        .certificate-field {
          margin-bottom: 1.125rem;

          .field-label {
            display: block;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.9rem;
            font-weight: 900;
            color: #8b5a2b;
            margin-bottom: 0.625rem;
            text-decoration: underline;
          }

          .diagnosis-text {
            margin: 0;
            padding: 0.625rem 0.875rem;
            background: #fff;
            border: 0.125rem solid #ff4b4b;
            color: #d63031;
            font-family: 'Courier New', Courier, monospace;
            font-weight: 900;
            font-size: 1rem;
            line-height: 1.5;
            box-shadow: 0.25rem 0.25rem 0 rgba(255, 75, 75, 0.1);
          }

          .treatment-text {
            margin: 0;
            padding: 0 0.625rem;
            font-family: 'Courier New', Courier, monospace;
            font-size: 1rem;
            line-height: 1.65;
            white-space: pre-wrap;
            color: #333;
          }

          .field-value {
            font-family: monospace;
            font-weight: bold;
            font-size: 0.875rem;
          }
        }
      }

      .certificate-footer {
        border-top: 0.125rem solid #eee;
        padding-top: 1.25rem;
        padding-left: 1.25rem;

        .signature-section {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;

          .doctor-signature {
            .signature-label {
              font-family: 'Courier New', Courier, monospace;
              font-size: 0.6875rem;
              color: #999;
              margin-bottom: 0.625rem;
            }

            .signature-name {
              font-family: 'Courier New', Courier, monospace;
              font-size: 0.9375rem;
              font-weight: 900;
              color: #333;
              border-bottom: 0.125rem solid #333;
              padding-bottom: 0.3125rem;
              min-width: 13.75rem;
              font-style: italic;
            }
          }

          .hospital-stamp {
            .stamp-circle {
              width: 5.625rem;
              height: 5.625rem;
              border: 0.1875rem double #ff4b4b;
              display: flex;
              align-items: center;
              justify-content: center;
              transform: rotate(-12deg);
              opacity: 0.7;

              .stamp-text {
                text-align: center;
                color: #ff4b4b;
                font-weight: 900;

                .stamp-line1 { font-size: 0.625rem; }
                .stamp-line2 { font-size: 0.5625rem; margin-top: 0.125rem; }
                .stamp-star { font-size: 1.125rem; margin-top: 0.25rem; }
              }
            }
          }
        }
      }
    }

    .evaluation-actions {
      margin-top: 1.25rem;
      text-align: center;
    }

    .evaluation-section {
      margin-top: 2rem;
      border: 0.1875rem solid #333;
      padding: 1.25rem;
      background: #f9f9fc;
      box-shadow: 0.25rem 0.25rem 0 rgba(0,0,0,0.1);

      h5 {
        font-family: 'Courier New', Courier, monospace;
        font-weight: 900;
        font-size: 0.875rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: #333;
      }

      .evaluation-box {
        .evaluation-score {
          display: flex;
          align-items: center;
          gap: 0.9375rem;
          margin-bottom: 1.25rem;
          padding-bottom: 0.9375rem;
          border-bottom: 0.0625rem dashed #ccc;

          .score-label {
            font-family: monospace;
            font-size: 0.75rem;
            font-weight: bold;
            color: #666;
          }

          .score-value {
            font-family: 'Press Start 2P', cursive;
            font-size: 1.125rem;
          }
        }

        .evaluation-subscores {
          display: flex;
          flex-direction: column;
          gap: 0.9375rem;
          margin-bottom: 1.25rem;

          .subscore-item {
            .subscore-label {
              display: block;
              font-family: monospace;
              font-size: 0.6875rem;
              color: #7f8c8d;
              margin-bottom: 0.5rem;
            }

            :deep(.el-progress-bar__outer) {
              border-radius: 0;
              background-color: #eee;
              border: 0.0625rem solid #ddd;
            }
            :deep(.el-progress-bar__inner) {
              border-radius: 0;
            }
          }
        }

        .evaluation-reasoning {
          background: #fff;
          padding: 0.9375rem;
          border: 0.0625rem solid #eee;

          strong {
            font-family: monospace;
            font-size: 0.6875rem;
            color: #999;
            display: block;
            margin-bottom: 0.625rem;
            text-transform: uppercase;
          }

          p {
            margin: 0;
            font-size: 0.8125rem;
            line-height: 1.6;
            color: #333;
          }
        }
      }
    }

    .result-section {
      margin-top: 2rem;

      h5 {
        font-family: 'Courier New', Courier, monospace;
        font-weight: 900;
        font-size: 0.875rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
      }

      .result-box {
        padding: 1.25rem;
        border: 0.1875rem solid #333;
        box-shadow: 0.25rem 0.25rem 0 rgba(0,0,0,0.1);

        &.success {
          background: #eef9f5;
          border-color: #3a7b5e;
          .result-label { color: #3a7b5e; }
        }

        &.warning {
          background: #fff8ee;
          border-color: #e67e22;
          .result-label { color: #e67e22; }
        }

        .result-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.75rem;

          .result-label {
            font-weight: 900;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.9375rem;
          }

          .result-score {
            font-family: monospace;
            font-weight: bold;
            font-size: 0.8125rem;
          }
        }

        .result-feedback {
          font-size: 0.8125rem;
          line-height: 1.6;
          color: #333;
        }
      }
    }
  }
}
</style>
