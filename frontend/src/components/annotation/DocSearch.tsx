import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'

interface DocSearchProps {
  className?: string
}

/**
 * Jump-to-doc input. Not a filter — submitting navigates straight to
 * /docs/{id}. Lets users paste a known document_id from a notification,
 * email, or audit log and land on the editor without scanning the feed.
 *
 * If the id doesn't exist, the DocViewer page surfaces the 404; we do
 * not pre-validate here because that would require an extra round-trip
 * for every keystroke commit.
 */
export function DocSearch({ className }: DocSearchProps) {
  const navigate = useNavigate()
  const [value, setValue] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const trimmed = value.trim()
    if (trimmed.length === 0) return
    navigate(`/docs/${encodeURIComponent(trimmed)}`)
    setValue('')
  }

  return (
    <form
      onSubmit={handleSubmit}
      role="search"
      aria-label="Doküman ID ile ara"
      className={className}
    >
      <div className="relative">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Doc № veya ID ara…"
          aria-label="Doküman ID"
          className="h-10 pl-9 font-mono text-[14px]"
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="off"
        />
      </div>
    </form>
  )
}
