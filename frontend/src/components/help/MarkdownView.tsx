import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'

// CRITICAL: do NOT add rehype-raw. It bypasses sanitization. Spec §7.2.
const allowedTags = [
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'p', 'br', 'hr',
  'ul', 'ol', 'li',
  'strong', 'em', 'code', 'pre', 'blockquote',
  'a', 'img',
  'table', 'thead', 'tbody', 'tr', 'td', 'th',
]

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: allowedTags,
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), ['target']],
  },
}

interface MarkdownViewProps {
  children: string
}

export function MarkdownView({ children }: MarkdownViewProps) {
  return (
    <div className="prose prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
