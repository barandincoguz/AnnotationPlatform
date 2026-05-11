import type { ReactNode } from 'react'

interface ResizableColumnsProps {
  left: ReactNode
  middle: ReactNode
  right: ReactNode
}

export function ResizableColumns({ left, middle, right }: ResizableColumnsProps) {
  return (
    <div className="grid h-full w-full grid-cols-[30%_40%_30%] overflow-hidden">
      <div className="border-r border-border overflow-hidden">{left}</div>
      <div className="border-r border-border overflow-hidden">{middle}</div>
      <div className="overflow-hidden">{right}</div>
    </div>
  )
}
