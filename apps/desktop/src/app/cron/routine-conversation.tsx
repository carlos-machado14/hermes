import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { converseRoutine, type CronJob } from '@/hermes'
import type { Translations } from '@/i18n'
import { asText } from '@/lib/text'
import { notifyError } from '@/store/notifications'

interface ChatMessage {
  role: 'assistant' | 'user'
  content: string
}

interface RoutineConversationProps {
  c: Translations['cron']
  job?: CronJob | null
  onChanged: (routine: CronJob | null) => void | Promise<void>
}

function routineSummary(job: CronJob | null | undefined): string {
  if (!job) {
    return ''
  }

  const schedule = asText(job.schedule_display) || asText(job.schedule?.display) || asText(job.schedule?.expr)
  const state = asText(job.state) || (job.enabled ? 'scheduled' : 'paused')

  return [schedule, state].filter(Boolean).join(' · ')
}

export function RoutineConversation({ c, job, onChanged }: RoutineConversationProps) {
  const [conversationId, setConversationId] = useState<string>()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [value, setValue] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => {
    setConversationId(undefined)
    setMessages([])
    setValue('')
  }, [job?.id])

  async function send() {
    const message = value.trim()

    if (!message || sending) {
      return
    }

    setValue('')
    setMessages(current => [...current, { role: 'user', content: message }])
    setSending(true)

    try {
      const response = await converseRoutine({
        message,
        ...(conversationId ? { conversation_id: conversationId } : {}),
        ...(job?.id ? { routine_id: job.id } : {})
      })

      setConversationId(response.conversation_id)
      setMessages(current => [...current, response.message])
      await onChanged(response.routine)
    } catch (error) {
      notifyError(error, c.failedUpdate)
      setMessages(current => [
        ...current,
        { role: 'assistant', content: c.failedUpdate }
      ])
    } finally {
      setSending(false)
    }
  }

  const selectedSummary = routineSummary(job)

  return (
    <section className="space-y-2 rounded-md border border-border/70 bg-background/35 p-3">
      <div className="space-y-0.5">
        <div className="flex items-center justify-between gap-2">
          <h4 className="text-xs font-semibold text-foreground">Hermes</h4>
          {selectedSummary ? (
            <span className="truncate text-[0.65rem] text-muted-foreground">{selectedSummary}</span>
          ) : null}
        </div>
        <p className="text-[0.7rem] text-muted-foreground">
          {job ? c.editDesc : c.createDesc}
        </p>
      </div>

      {messages.length > 0 ? (
        <div className="max-h-56 space-y-2 overflow-y-auto rounded-md bg-muted/20 p-2">
          {messages.map((message, index) => (
            <div
              className={
                message.role === 'user'
                  ? 'ml-8 rounded-md bg-primary/10 px-2.5 py-2 text-xs text-foreground'
                  : 'mr-8 rounded-md bg-muted px-2.5 py-2 text-xs text-foreground'
              }
              key={`${message.role}-${index}`}
            >
              {message.content}
            </div>
          ))}
        </div>
      ) : null}

      <div className="flex items-end gap-2">
        <Textarea
          className="min-h-20 resize-none text-sm"
          disabled={sending}
          onChange={event => setValue(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void send()
            }
          }}
          placeholder={
            job
              ? 'Diga o que deseja alterar nesta rotina…'
              : 'Ex.: Todo dia às 8h procure 3 empresas sem site e me traga os contatos…'
          }
          value={value}
        />
        <Button disabled={sending || !value.trim()} onClick={() => void send()} size="sm">
          {sending ? c.loading : job ? c.saveChanges : c.createAction}
        </Button>
      </div>
    </section>
  )
}
