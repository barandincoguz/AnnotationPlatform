import { ApiError } from '@/api/client'

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError
}

export function is409(err: unknown, code?: string): err is ApiError {
  return isApiError(err) && err.status === 409 && (code === undefined || err.code === code)
}

export function is409AlreadySubmittedQuiz(err: unknown): err is ApiError {
  return is409(err, 'quiz_already_submitted')
}

export function is409AlreadySubmittedDoc(err: unknown): err is ApiError {
  return is409(err, 'gold_doc_already_submitted')
}

export function is409AlreadyPassed(err: unknown): err is ApiError {
  return is409(err, 'already_passed')
}

export function is403LockedOut(err: unknown): err is ApiError {
  return isApiError(err) && err.status === 403 && err.code === 'max_attempts_reached'
}
