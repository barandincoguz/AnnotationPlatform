import { z } from 'zod'

const envSchema = z.object({
  VITE_API_BASE_URL: z.string().default(''),
})

const viteEnv = import.meta.env as unknown as Record<string, unknown>
const rawEnv: unknown = {
  VITE_API_BASE_URL: viteEnv.VITE_API_BASE_URL,
}
export const env = envSchema.parse(rawEnv)
