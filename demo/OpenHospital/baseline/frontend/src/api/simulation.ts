import { request } from './request'
import type { SimulationStatus, SimulationStatistics } from '@/types'

export const simulationApi = {
  getStatus(): Promise<SimulationStatus> {
    return request.get('/simulation/status')
  },
  getStatistics(): Promise<SimulationStatistics> {
    return request.get('/simulation/statistics')
  },
}
