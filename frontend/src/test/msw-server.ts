import { setupServer } from 'msw/node'
import { handlers } from './msw-handlers'

// Shared MSW server. Default handlers come from msw-handlers.ts (T6 expands
// the list). Individual tests add per-test handlers via server.use(...).
export const server = setupServer(...handlers)
