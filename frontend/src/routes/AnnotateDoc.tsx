import { useParams } from 'react-router-dom'

export function AnnotateDoc() {
  const { docId } = useParams()
  return (
    <div className="p-4 text-sm text-muted-foreground">
      AnnotateDoc placeholder (will be implemented in T18). docId={docId}
    </div>
  )
}
