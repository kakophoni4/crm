import { Web } from 'sip.js'

import type { TelephonyWebrtcConfig } from './api'

type SimpleUser = InstanceType<typeof Web.SimpleUser>

export type SoftphoneStatus = 'idle' | 'connecting' | 'registered' | 'calling' | 'in-call' | 'ended'

export interface SoftphoneEvents {
  onStatus?: (status: SoftphoneStatus) => void
  onError?: (message: string) => void
}

const BASE_AUDIO_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
}

export class CrmSoftphone {
  private user: SimpleUser | null = null
  private accountDomain = ''

  constructor(private readonly events: SoftphoneEvents = {}) {}

  async connect(config: TelephonyWebrtcConfig, remoteAudio: HTMLAudioElement): Promise<void> {
    await this.disconnect()
    // Fail early with a clear message if Windows/browser has no usable mic.
    await ensureMicrophoneAvailable()
    const domain = sipDomain(config.sip_uri)
    this.accountDomain = domain
    this.events.onStatus?.('connecting')
    const user = new Web.SimpleUser(config.ws_url, {
      aor: config.sip_uri,
      media: {
        // sip.js SimpleUser types expect boolean; mic check/constraints run in
        // ensureMicrophoneAvailable() before connect/call.
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
      'Микрофон не найден. Подключите гарнитуру/микрофон, в Windows сделайте его устройством ' +
      'ввода по умолчанию и обновите страницу телефонии.'
    )
  }
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || text.includes('permission')) {
    return 'Нет доступа к микрофону. Разрешите доступ в адресной строке браузера и повторите звонок.'
  }
  if (name === 'NotReadableError' || name === 'AbortError' || text.includes('could not start audio')) {
    return 'Микрофон занят другим приложением (Zoom, Teams, Discord). Закройте их и повторите.'
  }
  if (name === 'OverconstrainedError') {
    return 'Выбранный микрофон недоступен. Обновите страницу и попробуйте снова.'
  }
  return raw || 'Не удалось начать звонок'
}

async function ensureMicrophoneAvailable(): Promise<void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Браузер не поддерживает доступ к микрофону (нужен HTTPS или localhost)')
  }

  let stream: MediaStream | null = null
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { ...BASE_AUDIO_CONSTRAINTS },
      video: false,
    })
  } catch (firstErr) {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      const inputs = devices.filter(
        (d) => d.kind === 'audioinput' && d.deviceId && d.deviceId !== 'default',
      )
      if (inputs.length === 0) {
        throw firstErr
      }
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          ...BASE_AUDIO_CONSTRAINTS,
          deviceId: { exact: inputs[0].deviceId },
        },
        video: false,
      })
    } catch (secondErr) {
      throw new Error(mapMediaError(secondErr))
    }
  } finally {
    stream?.getTracks().forEach((t) => t.stop())
  }
}
