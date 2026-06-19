import { describe, it, expect } from 'vitest'
import {
  helpResponseSchema,
  startResponseSchema,
  quizSubmitResponseSchema,
  annotateSubmitResponseSchema,
} from './trainingSchemas'

describe('Zod schemas', () => {
  describe('helpResponseSchema', () => {
    it('accepts valid sections', () => {
      const valid = {
        sections: [
          { id: '01-welcome', order: 1, title: 'Hoş geldin', body: '# Hoş geldin\n…' },
        ],
      }
      expect(() => helpResponseSchema.parse(valid)).not.toThrow()
    })

    it('rejects missing sections', () => {
      expect(() => helpResponseSchema.parse({})).toThrow()
    })

    it('rejects malformed section', () => {
      expect(() =>
        helpResponseSchema.parse({ sections: [{ id: 1, order: '1', title: '', body: '' }] }),
      ).toThrow()
    })
  })

  describe('startResponseSchema', () => {
    const valid = {
      attempt_id: 42,
      attempt_number: 1,
      questions: Array.from({ length: 5 }, (_, i) => ({
        id: `q${i + 1}`,
        text: `Soru ${i + 1}`,
        choices: ['a', 'b', 'c', 'd'],
      })),
      gold_docs: [
        { gold_id: 'sample_kvk_5', content: '…' },
        { gold_id: 'sample_kdv_29', content: '…' },
        { gold_id: 'sample_gvk_67', content: '…' },
      ],
    }

    it('accepts well-formed payload', () => {
      expect(() => startResponseSchema.parse(valid)).not.toThrow()
    })

    it('rejects wrong question count', () => {
      const bad = { ...valid, questions: valid.questions.slice(0, 3) }
      expect(() => startResponseSchema.parse(bad)).toThrow()
    })

    it('rejects wrong gold_doc count', () => {
      const bad = { ...valid, gold_docs: valid.gold_docs.slice(0, 2) }
      expect(() => startResponseSchema.parse(bad)).toThrow()
    })

    it('rejects choices length != 4', () => {
      const bad = {
        ...valid,
        questions: [
          { ...valid.questions[0], choices: ['a', 'b'] },
          ...valid.questions.slice(1),
        ],
      }
      expect(() => startResponseSchema.parse(bad)).toThrow()
    })
  })

  describe('quizSubmitResponseSchema', () => {
    it('accepts {score, total}', () => {
      expect(() => quizSubmitResponseSchema.parse({ score: 3, total: 5, results: [] })).not.toThrow()
    })
    it('rejects floats', () => {
      expect(() => quizSubmitResponseSchema.parse({ score: 3.5, total: 5 })).toThrow()
    })
  })

  describe('annotateSubmitResponseSchema', () => {
    it('accepts full shape', () => {
      expect(() =>
        annotateSubmitResponseSchema.parse({
          passed: true,
          matched_count: 2,
          expected_count: 2,
          min_concept_count: 1,
          expected_concepts: [{ kanun_no: '5520', madde: '5' }],
        }),
      ).not.toThrow()
    })
    it('rejects missing passed', () => {
      expect(() =>
        annotateSubmitResponseSchema.parse({
          matched_count: 2,
          expected_count: 2,
          min_concept_count: 1,
        }),
      ).toThrow()
    })
  })
})
