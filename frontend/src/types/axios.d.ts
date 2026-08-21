import 'axios'

declare module 'axios' {
  interface AxiosRequestConfig {
    suppressGlobalError?: boolean
  }
}
