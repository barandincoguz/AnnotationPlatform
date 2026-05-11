import { describe, it, expect } from 'vitest'
import { ApiError } from '@/api/client'
import {
  isApiError,
  is409,
  is409AlreadySubmittedQuiz,
  is409AlreadySubmittedDoc,
  is409AlreadyPassed,
  is403LockedOut,
} from './apiError'

describe('apiError type guards', () => {
  it('isApiError true for ApiError instance', () => {
    expect(isApiError(new ApiError(409, 'foo', 'bar'))).toBe(true)
  })

  it('isApiError false for plain Error', () => {
    expect(isApiError(new Error('x'))).toBe(false)
  })

  it('isApiError false for non-error', () => {
    expect(isApiError({ status: 409 })).toBe(false)
    expect(isApiError(null)).toBe(false)
    expect(isApiError('foo')).toBe(false)
  })

  it('is409 matches status without code constraint', () => {
    expect(is409(new ApiError(409, 'any_code', 'm'))).toBe(true)
    expect(is409(new ApiError(403, 'any_code', 'm'))).toBe(false)
  })

  it('is409 with code matches both', () => {
    expect(is409(new ApiError(409, 'foo', 'm'), 'foo')).toBe(true)
    expect(is409(new ApiError(409, 'bar', 'm'), 'foo')).toBe(false)
  })

  it('is409AlreadySubmittedQuiz', () => {
    expect(is409AlreadySubmittedQuiz(new ApiError(409, 'quiz_already_submitted', 'm'))).toBe(true)
    expect(is409AlreadySubmittedQuiz(new ApiError(409, 'gold_doc_already_submitted', 'm'))).toBe(false)
  })

  it('is409AlreadySubmittedDoc', () => {
    expect(is409AlreadySubmittedDoc(new ApiError(409, 'gold_doc_already_submitted', 'm'))).toBe(true)
    expect(is409AlreadySubmittedDoc(new ApiError(409, 'quiz_already_submitted', 'm'))).toBe(false)
  })

  it('is409AlreadyPassed', () => {
    expect(is409AlreadyPassed(new ApiError(409, 'already_passed', 'm'))).toBe(true)
    expect(is409AlreadyPassed(new ApiError(409, 'other', 'm'))).toBe(false)
  })

  it('is403LockedOut', () => {
    expect(is403LockedOut(new ApiError(403, 'max_attempts_reached', 'm'))).toBe(true)
    expect(is403LockedOut(new ApiError(403, 'other', 'm'))).toBe(false)
    expect(is403LockedOut(new ApiError(409, 'max_attempts_reached', 'm'))).toBe(false)
  })
})
