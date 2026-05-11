import { useState, type FormEvent } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError } from '@/api/client'

export function Register() {
  const { registerMutation } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const disabled = !username || !password || !inviteCode

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    registerMutation.mutate({ username, password, invite_code: inviteCode })
  }

  const errorMessage =
    registerMutation.error instanceof ApiError
      ? registerMutation.error.message
      : registerMutation.isError
        ? 'Kayıt başarısız'
        : null

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Kayıt Ol</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Kullanıcı adı</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Şifre</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="invite">Davet kodu</Label>
              <Input
                id="invite"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
              />
            </div>
            {errorMessage && (
              <p className="text-sm text-destructive" role="alert">
                {errorMessage}
              </p>
            )}
            <Button
              type="submit"
              disabled={disabled || registerMutation.isPending}
              className="w-full"
            >
              {registerMutation.isPending ? 'Gönderiliyor…' : 'Kayıt ol'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
