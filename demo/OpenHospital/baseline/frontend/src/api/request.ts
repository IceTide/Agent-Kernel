import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
const service: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})
service.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)
service.interceptors.response.use(
  (response: AxiosResponse) => {
    return response.data
  },
  (error) => {
    const message = error.response?.data?.message || error.message || '请求Failed'
    ElMessage.error(message)
    console.error('Response error:', error)
    return Promise.reject(error)
  }
)
export const request = {
  get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return service.get(url, config)
  },
  
  post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return service.post(url, data, config)
  },
  
  put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return service.put(url, data, config)
  },
  
  delete<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return service.delete(url, config)
  },
}
export function createCancelableRequest<T>(
  requestFn: (signal: AbortSignal) => Promise<T>
): { promise: Promise<T>; abort: () => void } {
  const abortController = new AbortController()
  
  const promise = requestFn(abortController.signal).catch((error) => {
    if (error.name === 'AbortError' || error.name === 'CanceledError') {
      const cancelError = new Error('Request canceled')
      cancelError.name = 'CanceledError'
      throw cancelError
    }
    throw error
  })
  
  return {
    promise,
    abort: () => abortController.abort(),
  }
}

export default service

