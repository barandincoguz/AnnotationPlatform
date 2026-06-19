import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { AdminTable } from '@/components/admin/AdminTable'
import { TypedConfirmDialog } from '@/components/admin/TypedConfirmDialog'
import {
  useAdminUsers,
  usePromoteUserMutation, useDemoteUserMutation,
  useEnableUserMutation, useDisableUserMutation,
  useResetUserTrainingMutation, useRotateInviteMutation,
} from '@/api/queries/admin'
import type { AdminUser } from '@/lib/adminSchemas'

type ActionType = 'promote' | 'demote' | 'enable' | 'disable' | 'reset'

function StatusChip({ label, variant }: { label: string; variant: 'success' | 'warning' | 'muted' }) {
  const cls =
    variant === 'success'
      ? 'bg-success/15 text-success border border-success/30'
      : variant === 'warning'
      ? 'bg-warning/15 text-warning border border-warning/30'
      : 'bg-muted text-muted-foreground border border-transparent'
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.15em] ${cls}`}>
      {label}
    </span>
  )
}

const ACTION_META: Record<ActionType, { title: string; word: string; confirmLabel: string; variant: 'destructive' | 'default' }> = {
  promote: { title: 'Admin Yap', word: 'PROMOTE', confirmLabel: 'Yetki Ver', variant: 'default' },
  demote:  { title: 'Admin yetkisini kaldır', word: 'DEMOTE', confirmLabel: 'Kaldır', variant: 'destructive' },
  enable:  { title: 'Kullanıcıyı Aktif Et', word: 'ENABLE', confirmLabel: 'Aktif Et', variant: 'default' },
  disable: { title: 'Kullanıcıyı Devre Dışı Bırak', word: 'DISABLE', confirmLabel: 'Devre Dışı', variant: 'destructive' },
  reset:   { title: 'Eğitimi Sıfırla', word: 'RESET', confirmLabel: 'Sıfırla', variant: 'destructive' },
}

function generateInviteCode(): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
  let suffix = ''
  for (let i = 0; i < 6; i++) suffix += alphabet[Math.floor(Math.random() * alphabet.length)]
  return `BURSIYER-2026-${suffix}`
}

export function UsersPage() {
  const q = useAdminUsers()
  const [search, setSearch] = useState('')

  const [pendingAction, setPendingAction] = useState<{ user: AdminUser; type: ActionType } | null>(null)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteCode, setInviteCode] = useState<string | null>(null)

  const promote = usePromoteUserMutation()
  const demote = useDemoteUserMutation()
  const enable = useEnableUserMutation()
  const disable = useDisableUserMutation()
  const resetTraining = useResetUserTrainingMutation()
  const rotateInvite = useRotateInviteMutation()

  const mutationFor = (t: ActionType) => ({
    promote, demote, enable, disable, reset: resetTraining,
  })[t]

  const runAction = () => {
    if (!pendingAction) return
    const m = mutationFor(pendingAction.type)
    const captured = pendingAction
    m.mutate(captured.user.id, {
      onSuccess: () => {
        toast.success(`${ACTION_META[captured.type].title} tamamlandı`)
        setPendingAction(null)
      },
      onError: (err: unknown) => {
        const status = (err as { status?: number })?.status
        const message = (err as { message?: unknown })?.message
        if (status === 400 && typeof message === 'string' && message.includes('last active admin')) {
          toast.error('Son adminin demote edilemez')
        } else if (status === 404) {
          toast.error('Kullanıcı bulunamadı')
        } else if (status === 409) {
          toast.error('Zaten bu rolde')
        } else {
          toast.error('İşlem başarısız')
        }
        setPendingAction(null)
      },
    })
  }

  const onRotate = () => {
    const newCode = generateInviteCode()
    rotateInvite.mutate(newCode, {
      onSuccess: (data) => {
        const code = (data as { new_code?: string })?.new_code ?? newCode
        setInviteCode(code)
        setInviteOpen(true)
      },
      onError: () => toast.error('Davet kodu üretilemedi'),
    })
  }

  const filteredUsers = (q.data?.users ?? []).filter((u) => {
    if (search.trim()) {
      const s = search.toLowerCase()
      const inUsername = u.username.toLowerCase().includes(s)
      const inEmail = (u.email ?? '').toLowerCase().includes(s)
      if (!inUsername && !inEmail) return false
    }
    return true
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="mb-6 space-y-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            People · Users
          </p>
          <h1 className="font-display text-3xl font-medium tracking-tight">
            User Management
          </h1>
          <p className="text-sm text-muted-foreground max-w-prose">
            Manage roles, status, and training progress for every registered user.
          </p>
        </div>
        <Button onClick={onRotate} disabled={rotateInvite.isPending}>Davet Linki Üret</Button>
      </div>
      <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border/70 bg-card/40 p-4">
        <Input placeholder="Ara..." value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
      </div>

      <AdminTable<AdminUser>
        rows={filteredUsers}
        loading={q.isLoading}
        getRowKey={(u) => u.id}
        columns={[
          { key: 'username', header: 'Kullanıcı', render: (u) => u.username },
          { key: 'email', header: 'E-posta', render: (u) => u.email ?? '—' },
          { key: 'role', header: 'Rol', render: (u) => u.role },
          {
            key: 'status', header: 'Durum',
            render: (u) => u.is_active
              ? <StatusChip label="Aktif" variant="success" />
              : <StatusChip label="Devre dışı" variant="muted" />,
          },
          {
            key: 'training', header: 'Eğitim',
            render: (u) => u.has_passed_training
              ? <StatusChip label="Geçti" variant="success" />
              : <StatusChip label="Bekliyor" variant="warning" />,
          },
          { key: 'created', header: 'Kayıt', render: (u) => u.created_at.slice(0, 10) },
          {
            key: 'actions', header: '', render: (u) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" aria-label="Eylemler">⋯</Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  {u.role === 'user' && (
                    <DropdownMenuItem onClick={() => setPendingAction({ user: u, type: 'promote' })}>
                      Admin Yap
                    </DropdownMenuItem>
                  )}
                  {u.role === 'admin' && (
                    <DropdownMenuItem onClick={() => setPendingAction({ user: u, type: 'demote' })}>
                      Admin yetkisini kaldır
                    </DropdownMenuItem>
                  )}
                  {u.is_active && (
                    <DropdownMenuItem onClick={() => setPendingAction({ user: u, type: 'disable' })}>
                      Devre Dışı Bırak
                    </DropdownMenuItem>
                  )}
                  {!u.is_active && (
                    <DropdownMenuItem onClick={() => setPendingAction({ user: u, type: 'enable' })}>
                      Aktif Et
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onClick={() => setPendingAction({ user: u, type: 'reset' })}>
                    Eğitimi Sıfırla
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ),
          },
        ]}
      />

      {pendingAction && (
        <TypedConfirmDialog
          open={!!pendingAction}
          title={ACTION_META[pendingAction.type].title}
          body={<p><strong>{pendingAction.user.username}</strong> için bu işlemi onaylıyor musun?</p>}
          confirmWord={ACTION_META[pendingAction.type].word}
          confirmLabel={ACTION_META[pendingAction.type].confirmLabel}
          variant={ACTION_META[pendingAction.type].variant}
          isPending={mutationFor(pendingAction.type).isPending}
          onConfirm={runAction}
          onClose={() => setPendingAction(null)}
        />
      )}

      <Dialog open={inviteOpen} onOpenChange={(o) => { if (!o) { setInviteOpen(false); setInviteCode(null) } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Yeni Davet Kodu</DialogTitle>
            <DialogDescription>
              Eski davet kodu artık geçersizdir. Yeni kullanıcı kayıtlarında bu kodu kullanın.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded bg-muted p-3 font-mono text-sm">{inviteCode}</div>
          <DialogFooter>
            <Button onClick={() => {
              if (!inviteCode) return
              // Toast only AFTER the clipboard promise resolves; reject path
              // (insecure context, permission denied, page unfocused) was
              // previously swallowed by `void` so the user got a misleading
              // "Kopyalandı" even when nothing landed in the buffer.
              navigator.clipboard.writeText(inviteCode).then(
                () => toast.success('Kopyalandı'),
                () => toast.error('Kopyalanamadı'),
              )
            }}>
              Kopyala
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
