import { z } from 'zod'

export const helpSectionSchema = z.object({
  id: z.string(),
  order: z.number().int(),
  title: z.string(),
  body: z.string(),
})

export const helpResponseSchema = z.object({
  sections: z.array(helpSectionSchema),
})

export const questionSchema = z.object({
  id: z.string(),
  text: z.string(),
  choices: z.array(z.string()).length(4),
})

export const goldDocSchema = z.object({
  gold_id: z.string(),
  content: z.string(),
  // 16c.1: surfaced for the reveal panel. Permissive shape (dict) because
  // the per-concept keys vary across gold docs (kanun_no, kanun_ad, madde,
  // fikra, bent — any subset).
  expected_concepts: z.array(z.record(z.string(), z.string())).default([]),
  min_concept_count: z.number().int().default(1),
})

export const startResponseSchema = z.object({
  attempt_id: z.number().int(),
  attempt_number: z.number().int(),
  questions: z.array(questionSchema).length(5),
  gold_docs: z.array(goldDocSchema).length(3),
})

export const quizSubmitResponseSchema = z.object({
  score: z.number().int(),
  total: z.number().int(),
})

export const annotateSubmitResponseSchema = z.object({
  passed: z.boolean(),
  matched_count: z.number().int(),
  expected_count: z.number().int(),
  min_concept_count: z.number().int(),
})

export type HelpSection = z.infer<typeof helpSectionSchema>
export type HelpResponse = z.infer<typeof helpResponseSchema>
export type Question = z.infer<typeof questionSchema>
export type GoldDoc = z.infer<typeof goldDocSchema>
export type StartResponse = z.infer<typeof startResponseSchema>
export type QuizSubmitResponse = z.infer<typeof quizSubmitResponseSchema>
export type AnnotateSubmitResponse = z.infer<typeof annotateSubmitResponseSchema>
