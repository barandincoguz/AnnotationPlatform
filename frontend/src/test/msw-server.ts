import { setupServer } from 'msw/node'

// Shared MSW server. Default handlers land in T6's msw-handlers.ts.
// Individual tests add handlers via server.use(...).
export const server = setupServer()
