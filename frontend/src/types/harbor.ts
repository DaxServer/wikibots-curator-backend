export interface Process {
  type: string
  command: string
  args: string[]
  direct: boolean
  buildpackID: string
}
