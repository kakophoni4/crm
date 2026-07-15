import { Web } from 'sip.js'

import type { TelephonyWebrtcConfig } from './api'

type SimpleUser = InstanceType<typeof Web.SimpleUser>

export type SoftphoneStatus = 'idle' | 'connecting' | 'registered' | 'calling' | 'in-call' | 'ended'

export interface SoftphoneEvents {
  onStatus?: (status: SoftphoneStatus) => void
  onError?: (message: string) => void
  onWarning?: (message: string) => void
}

export class CrmSoftphone {
  private user: SimpleUser | null = null
  private accountDomain = ''
  private silenceHold: { ctx: AudioContext; osc: OscillatorNode } | null = null

  constructor(private readonly events: SoftphoneEvents = {}) {}

  async connect(config: TelephonyWebrtcConfig, remoteAudio: HTMLAudioElement): Promise<void> {
    await this.disconnect()
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
          // If Chrome has no usable mic, still place the call with a silent track.
          mediaStreamFactory: async () => {
            const acquired = await acquireLocalAudioStream()
            if (acquired.usedSilence) {
              this.silenceHold = acquired.hold
              this.events.onWarning?.(
                'Микрофон недоступен браузеру — звонок идёт без вашего голоса. ' +
                  'Windows → Конфиденциальность → Микрофон (разрешить Chrome), ' +
                  'устройство ввода по умолчанию, затем обновите страницу.',
              )
            } else {
              this.releaseSilenceHold()
            }
            return acquired.stream
          },
        },
      },
      delegate: {
        onCallAnswered: () => this.events.onStatus?.('in-call'),
        onCallCreated: () => this.events.onStatus?.('calling'),
        onCallHangup: () => {
          this.releaseSilenceHold()
          this.events.onStatus?.('ended')
        },
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
    const destination = `sip:${normalizeDialNumber(number)}@${this.accountDomain}`
    this.events.onStatus?.('calling')
    try {
      // Mic (or silent fallback) is acquired inside mediaStreamFactory during INVITE.
      await this.user.call(destination)
    } catch (err) {
      this.releaseSilenceHold()
      throw new Error(mapMediaError(err))
    }
  }

  async hangup(): Promise<void> {
    if (!this.user) {
      return
    }
    await this.user.hangup()
    this.releaseSilenceHold()
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
      this.releaseSilenceHold()
      return
    }
    const user = this.user
    this.user = null
    try {
      await user.unregister()
    } finally {
      await user.disconnect()
      this.releaseSilenceHold()
      this.events.onStatus?.('idle')
    }
  }

  private releaseSilenceHold(): void {
    const hold = this.silenceHold
    this.silenceHold = null
    if (!hold) return
    try {
      hold.osc.stop()
    } catch {
      /* already stopped */
    }
    void hold.ctx.close().catch(() => undefined)
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

async function acquireLocalAudioStream(): Promise<{
  stream: MediaStream
  usedSilence: boolean
  hold: { ctx: AudioContext; osc: OscillatorNode } | null
}> {
  if (typeof window !== 'undefined' && !window.isSecureContext) {
    throw new Error('Доступ к микрофону только по HTTPS. Откройте телефонию по защищённому адресу сайта.')
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    const silent = createSilentAudioStream()
    return { stream: silent.stream, usedSilence: true, hold: silent.hold }
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    return { stream, usedSilence: false, hold: null }
  } catch {
    try {
      await navigator.mediaDevices.enumerateDevices()
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      return { stream, usedSilence: false, hold: null }
    } catch {
      const silent = createSilentAudioStream()
      return { stream: silent.stream, usedSilence: true, hold: silent.hold }
    }
  }
}

function createSilentAudioStream(): {
  stream: MediaStream
  hold: { ctx: AudioContext; osc: OscillatorNode }
} {
  const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  const ctx = new Ctx()
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  const dest = ctx.createMediaStreamDestination()
  gain.gain.value = 0
  osc.connect(gain)
  gain.connect(dest)
  osc.start()
  return { stream: dest.stream, hold: { ctx, osc } }
}
