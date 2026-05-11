import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { AlertTriangle } from 'lucide-react'

interface State {
  hasError: boolean
  error: Error | null
}

interface Props {
  children: ReactNode
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    // Production: send to Sentry/etc. — Paket 17.
    console.error('ErrorBoundary caught:', error, info.componentStack)
  }

  handleReload = () => {
    window.location.reload()
  }

  override render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
          <AlertTriangle className="h-10 w-10 text-destructive" aria-hidden />
          <p className="text-lg font-medium">Bir şeyler ters gitti</p>
          <p className="text-sm text-muted-foreground">
            Beklenmeyen bir hata oluştu. Sayfayı yenileyerek tekrar deneyin.
          </p>
          <Button onClick={this.handleReload}>Sayfayı yenile</Button>
        </div>
      )
    }
    return this.props.children
  }
}
