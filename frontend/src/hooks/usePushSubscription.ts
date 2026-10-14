import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import { useStore } from '../store/useStore'

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

export function usePushSubscription() {
  const [isSupported, setIsSupported] = useState<boolean>(false)
  const [permission, setPermission] = useState<NotificationPermission>('default')
  const [isSubscribed, setIsSubscribed] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const proactiveSettings = useStore((s) => s.proactiveSettings)
  const updateProactiveSettings = useStore((s) => s.updateProactiveSettings)

  // Verifica suporte e estado atual
  useEffect(() => {
    const supported =
      typeof window !== 'undefined' &&
      'serviceWorker' in navigator &&
      'PushManager' in window &&
      'Notification' in window
    setIsSupported(supported)

    if (supported) {
      setPermission(Notification.permission)
      navigator.serviceWorker.ready
        .then((reg) => reg.pushManager.getSubscription())
        .then((sub) => {
          setIsSubscribed(!!sub)
        })
        .catch((err) => {
          console.debug('[Push] Falha ao verificar subscription:', err)
        })
    }
  }, [])

  const subscribe = useCallback(async () => {
    if (!isSupported) {
      setError('Notificações não suportadas neste navegador.')
      return false
    }

    setLoading(true)
    setError(null)

    try {
      // 1. Pedir permissão ao usuário
      const perm = await Notification.requestPermission()
      setPermission(perm)
      if (perm !== 'granted') {
        setError('Permissão de notificação negada.')
        setLoading(false)
        return false
      }

      // 2. Obter chave pública VAPID do backend
      const { publicKey } = await api.getVapidPublicKey()
      if (!publicKey) {
        throw new Error('Chave VAPID não configurada no servidor.')
      }

      // 3. Registrar no PushManager
      const registration = await navigator.serviceWorker.ready
      let subscription = await registration.pushManager.getSubscription()

      if (!subscription) {
        const applicationServerKey = urlBase64ToUint8Array(publicKey)
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: applicationServerKey as unknown as BufferSource,
        })
      }

      // 4. Enviar ao backend
      const subJson = subscription.toJSON()
      if (!subJson.keys?.p256dh || !subJson.keys?.auth) {
        throw new Error('Chaves da assinatura inválidas.')
      }

      await api.subscribePush({
        endpoint: subscription.endpoint,
        keys: {
          p256dh: subJson.keys.p256dh,
          auth: subJson.keys.auth,
        },
        user_agent: navigator.userAgent,
      })

      // 5. Atualizar preferências do usuário no backend e store
      await updateProactiveSettings({ push_enabled: true })

      setIsSubscribed(true)
      return true
    } catch (err: any) {
      const msg = err?.message || 'Erro ao registrar notificações nativas.'
      setError(msg)
      return false
    } finally {
      setLoading(false)
    }
  }, [isSupported, updateProactiveSettings])

  const unsubscribe = useCallback(async () => {
    if (!isSupported) return false

    setLoading(true)
    setError(null)

    try {
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.getSubscription()

      if (subscription) {
        await api.unsubscribePush(subscription.endpoint).catch(() => {})
        await subscription.unsubscribe()
      }

      await updateProactiveSettings({ push_enabled: false })
      setIsSubscribed(false)
      return true
    } catch (err: any) {
      setError(err?.message || 'Erro ao desativar notificações.')
      return false
    } finally {
      setLoading(false)
    }
  }, [isSupported, updateProactiveSettings])

  const sendTest = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.testPushNotification()
      return res
    } catch (err: any) {
      setError(err?.message || 'Falha ao enviar notificação de teste.')
      return { ok: false, sent: 0 }
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    isSupported,
    permission,
    isSubscribed: isSubscribed || !!proactiveSettings?.push_enabled,
    loading,
    error,
    subscribe,
    unsubscribe,
    sendTest,
  }
}
