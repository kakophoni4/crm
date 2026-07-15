import { Web } from 'sip.js'

import type { TelephonyWebrtcConfig } from './api'

type SimpleUser = InstanceType<typeof Web.SimpleUser>

export type SoftphoneStatus = 'idle' | 'connecting' | 'registered' | 'calling' | 'in-call' | 'ended'

export interface SoftphoneEvents {
  onStatus?: (status: SoftphoneStatus) => void
  onError?: (message: string) => void
}

export class CrmSoftphone {
  private user: SimpleUser | null = null
  private accountDomain = ''

  constructor(private readonly events: SoftphoneEvents = {}) {}

  async connect(config: TelephonyWebrtcConfig, remoteAudio: HTMLAudioElement): Promise<void> {
    await this.disconnect()
    // Do not probe the mic here — SIP register works without it, and a probe with
    // constraints often throws NotFoundError before Chrome shows the permission UI.
    const domain = sipDomain(config.sip_uri)
    this.accountDomain = domain
    this.events.onStatus?.('connecting')
    const user = new Web.SimpleUser(config.ws_url, {
      aor: config.sip_uri,
      media: {
        constraints: { audio: true, video: false },
        remote: { audio: remoteAudio },
      },
      userAgentOptions: {
        authorizationPassword: config.extension_password,
        authorizationUsername: config.extension,
        displayName: config.display_name ?? config.extension,
        sessionDescriptionHandlerFactoryOptions: {
          peerConnectionConfiguration: {
            iceServers: config.ice_servers as RTCIceServer[],
          },
        },
      },
      delegate: {
        onCallAnswered: () => this.events.onStatus?.('in-call'),
        onCallCreated: () => this.events.onStatus?.('calling'),
        onCallHangup: () => this.events.onStatus?.('ended'),
        onServerConnect: () => this.events.onStatus?.('connecting'),
        onServerDisconnect: () => this.events.onStatus?.('idle'),
      },
    })
    this.user = user
    await user.connect()
    await user.register()
    this.events.onStatus?.('registered')
  }

  async call(number: string): Promise<void> {
    if (!this.user || !this.accountDomain) {
      throw new Error('Softphone is not connected')
    }
    // Permission prompt appears here with the simplest constraint.
    await ensureMicrophoneAvailable()
    const destination = `sip:${normalizeDialNumber(number)}@${this.accountDomain}`
    this.events.onStatus?.('calling')
    try {
      await this.user.call(destination)
    } catch (err) {
      throw new Error(mapMediaError(err))
    }
  }

  async hangup(): Promise<void> {
    if (!this.user) {
      return
    }
    await this.user.hangup()
    this.events.onStatus?.('ended')
  }

  mute(): void {
    this.user?.mute()
  }

  unmute(): void {
    this.user?.unmute()
  }

  getRemoteMediaStream(): MediaStream | undefined {
    return this.user?.remoteMediaStream
  }

  getLocalMediaStream(): MediaStream | undefined {
    return this.user?.localMediaStream
  }

  async disconnect(): Promise<void> {
    if (!this.user) {
      return
    }
    const user = this.user
    this.user = null
    try {
      await user.unregister()
    } finally {
      await user.disconnect()
      this.events.onStatus?.('idle')
    }
  }
}

function sipDomain(uri: string): string {
  const atIndex = uri.indexOf('@')
  return atIndex >= 0 ? uri.slice(atIndex + 1) : uri.replace(/^sip:/, '')
}

function normalizeDialNumber(value: string): string {
  return value.trim().replace(/[^\d+#*]/g, '')
}

export function mapMediaError(err: unknown): string {
  const name = err instanceof DOMException ? err.name : ''
  const raw = err instanceof Error ? err.message : String(err ?? '')
  const text = raw.toLowerCase()

  if (
    name === 'NotFoundError' ||
    name === 'DevicesNotFoundError' ||
    text.includes('requested device not found') ||
    text.includes('device not found')
  ) {
    return (
      'Браузер не видит микрофон. Проверьте: Параметры Windows → Конфиденциальность → Микрофон ' +
      '(доступ для приложений и для Chrome/Edge), устройство ввода по умолчанию, затем обновите страницу.'
    )
  }
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || text.includes('permission')) {
    return (
      'Нет доступа к микрофону. Нажмите на иконку замка слева от адреса сайта → Микрофон → Разрешить, ' +
      'обновите страницу и повторите.'
    )
  }
  if (name === 'NotReadableError' || name === 'AbortError' || text.includes('could not start audio')) {
    return 'Микрофон занят другим приложением (Zoom, Teams, Discord). Закройте их и повторите.'
  }
  if (name === 'OverconstrainedError') {
    return 'Выбранный микрофон недоступен. Обновите страницу и попробуйте снова.'
  }
  if (text.includes('secure context') || text.includes('https')) {
    return 'Доступ к микрофону только по HTTPS. Откройте телефонию по защищённому адресу сайта.'
  }
  return raw || 'Не удалось начать звонок'
}

/** Ask for mic with the simplest constraints so the browser shows the permission dialog. */
async function ensureMicrophoneAvailable(): Promise<void> {
  if (typeof window !== 'undefined' && !window.isSecureContext) {
    throw new Error('Доступ к микрофону только по HTTPS. Откройте телефонию по защищённому адресу сайта.')
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Браузер не поддерживает доступ к микрофону (нужен HTTPS)')
  }

  let stream: MediaStream | null = null
  try {
    // Bare `audio: true` is what actually triggers the permission prompt.
    stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
  } catch (firstErr) {
    // Retry once after enumerating — some Chrome builds only list inputs after a failed attempt.
    try {
      await navigator.mediaDevices.enumerateDevices()
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    } catch (secondErr) {
      throw new Error(mapMediaError(secondErr ?? firstErr))
    }
  } finally {
    stream?.getTracks().forEach((t) => t.stop())
  }
}
