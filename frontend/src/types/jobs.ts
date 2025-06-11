export interface Job {
  name: string
  cmd: string
  status_short: string
  status_long: string
  image: string
  id?: string
  created_at?: string
  updated_at?: string
  exit_code?: number | null
  error?: string | null
  pid?: number
  container_id?: string
  container_name?: string
  container_image?: string
  container_status?: string
}

export interface JobRequest {
  name: string
  cmd: string
  imagename: string
  continuous?: boolean
}
