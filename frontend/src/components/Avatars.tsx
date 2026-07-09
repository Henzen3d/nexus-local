import { User, Bot, AlertCircle, Wrench, Settings, Blocks } from 'lucide-react'

export function UserAvatar() {
  return (
    <div className="message-avatar user">
      <User size={16} />
    </div>
  )
}

export function AssistantAvatar() {
  return (
    <div className="message-avatar assistant">
      <Bot size={16} />
    </div>
  )
}

export function SystemAvatar() {
  return (
    <div className="message-avatar system">
      <Settings size={16} />
    </div>
  )
}

export function ToolAvatar() {
  return (
    <div className="message-avatar tool">
      <Wrench size={16} />
    </div>
  )
}

export function ErrorAvatar() {
  return (
    <div className="message-avatar error">
      <AlertCircle size={16} />
    </div>
  )
}

export function PluginAvatar() {
  return (
    <div className="message-avatar plugin">
      <Blocks size={16} />
    </div>
  )
}
