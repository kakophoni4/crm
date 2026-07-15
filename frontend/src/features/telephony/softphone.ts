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
          // Own factory: never let a mic glitch abort the SIP INVITE.
          mediaStreamFactory: async () => {
            const acquired = await acquireLocalAudioStream()
            if (acquired.usedSilence) {
              this.silenceHold = acquired.hold
              this.events.onWarning?.(
                'Звонок без микрофона (тишина). Если собеседник вас не слышит — проверьте устройство ввода в Windows.',
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
      await this.user.call(destination)
    } catch (err) {
      this.releaseSilenceHold()
      throw new Error(formatCallError(err))
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

/** Only map real getUserMedia DOMExceptions — not SIP/Bitcall "device" errors. */
function isGetUserMediaNotFound(err: unknown): boolean {
  if (!(err instanceof DOMException)) return false
  return err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError'
}

function isGetUserMediaPermission(err: unknown): boolean {
  if (!(err instanceof DOMException)) return false
  return err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError'
}

export function formatCallError(err: unknown): string {
  // Do NOT treat generic "device not found" strings as mic errors —
  // Bitcall/Asterisk often returns that for a missing SIP endpoint/extension.
  if (isGetUserMediaNotFound(err)) {
    return (
      'Браузер не видит аудиовход (это не про разрешение сайта). ' +
      'Windows → Конфиденциальность → Микрофон → доступ для Chrome, ' +
      'и устройство ввода по умолчанию.'
    )
  }
  if (isGetUserMediaPermission(err)) {
    return 'Сайт без доступа к микрофону (замок у адреса → Микрофон → Разрешить).'
  }
  if (err instanceof DOMException && (err.name === 'NotReadableError' || err.name === 'AbortError')) {
    return 'Микрофон занят другим приложением. Закройте Zoom/Teams/Discord и повторите.'
  }

  const raw = err instanceof Error ? err.message : String(err ?? '')
  const text = raw.toLowerCase()
  if (
    text.includes('device not found') ||
    text.includes('not found') ||
    text.includes('404') ||
    text.includes('user not registered') ||
    text.includes('temporarily unavailable') ||
    text.includes('486') ||
    text.includes('503')
  ) {
    return (
      `Ошибка линии Bitcall/SIP: ${raw || 'device/endpoint not found'}. ` +
      'Проверьте SIP-аккаунт, extension и что линия зарегистрирована (статус «Готово»).'
    )
  }
  return raw || 'Не удалось начать звонок'
}

/** @deprecated use formatCallError — kept for telephony page imports */
export function mapMediaError(err: unknown): string {
  return formatCallError(err)
}

async function acquireLocalAudioStream(): Promise<{
  stream: MediaStream
  usedSilence: boolean
  hold: { ctx: AudioContext; osc: OscillatorNode } | null
}> {
  if (!navigator.mediaDevices?.getUserMedia) {
    const silent = createSilentAudioStream()
    return { stream: silent.stream, usedSilence: true, hold: silent.hold }
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    return { stream, usedSilence: false, hold: null }
  } catch {
    // Never fail the call because of mic — outbound INVITE still goes with silence.
    const silent = createSilentAudioStream()
    return { stream: silent.stream, usedSilence: true, hold: silent.hold }
  }
}

function createSilentAudioStream(): {
  stream: MediaStream
  hold: { ctx: AudioContext; osc: OscillatorNode }
} {
  const Ctx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
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
