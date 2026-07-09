import { useState, useRef } from 'react'
import { Paperclip, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { Attachment } from '../types'

interface Props {
  onUploadStart: () => void
  onUploadSuccess: (attachment: Attachment) => void
  onUploadError: (error: string) => void
  currentModelId: string | null
  disabled?: boolean
}

export function AttachmentButton({
  onUploadStart,
  onUploadSuccess,
  onUploadError,
  currentModelId,
  disabled = false
}: Props) {
  const { t } = useTranslation()
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleButtonClick = () => {
    if (uploading || disabled || !currentModelId) return
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0 || !currentModelId) return

    setUploading(true)
    onUploadStart()

    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        
        const MAX_SIZE = 20 * 1024 * 1024 // 20MB
        if (file.size > MAX_SIZE) {
          throw new Error(t('artifacts.fileTooLarge', { name: file.name }))
        }

        const res = await api.uploadAttachment(file, currentModelId)
        onUploadSuccess(res)
      }
    } catch (err: any) {
      console.error('[Upload error]', err)
      onUploadError(err?.message || t('artifacts.uploadError'))
    } finally {
      setUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  return (
    <div className="attachment-button-container">
      <button
        type="button"
        className={`attachment-btn-chat ${uploading ? 'loading' : ''}`}
        onClick={handleButtonClick}
        disabled={disabled || uploading || !currentModelId}
        title={!currentModelId ? t('artifacts.selectModelFirst') : t('artifacts.attachFiles')}
      >
        {uploading ? (
          <Loader2 size={16} className="spin text-primary" />
        ) : (
          <Paperclip size={16} />
        )}
      </button>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        style={{ display: 'none' }}
        multiple
        accept=".pdf,.docx,.txt,.csv,.md,.png,.jpg,.jpeg,.webp"
      />
    </div>
  )
}
