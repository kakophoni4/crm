import { Web } from 'sip.js'

import type { TelephonyWebrtcConfig } from './api'

type SimpleUser = InstanceType<typeof Web.SimpleUser>

export type SoftphoneStatus = 'idle' | 'connecting' | 'registered' | 'calling' | 'in-call' | 'ended'

export interface SoftphoneEvents {
  onStatus?: (status: SoftphoneStatus) => void
  onError?: (message: string) => void
}

/**
 * Softphone: real microphone required. No silent fake stream — no mic → no INVITE.
 */
export class CrmSoftphone {
  private user: SimpleUser | null = null
  private accountDomain = ''
  private localStream: MediaStream | null = null

  constructor(private readonly events: SoftphoneEvents = {}) {}

  async connect(config: TelephonyWebrtcConfig, remoteAudio: HTMLAudioElement): Promise<void> {
    await this.disconnect()
    // Fail registration path early if mic is unusable — operator must fix device first.
    await this.ensureLocalMic()
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
          mediaStreamFactory: async () => {
            // Always a live mic track — never silence.
            return this.ensureLocalMic()
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
    // Hard gate: no microphone → no SIP INVITE, no CRM “failed” after half-dial.
    await this.ensureLocalMic()
    const destination = `sip:${normalizeDialNumber(number)}@${this.accountDomain}`
    this.events.onStatus?.('calling')
    try {
      await this.user.call(destination)
    } catch (err) {
      throw new Error(formatCallError(err))
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
    for (const track of this.localStream?.getAudioTracks() ?? []) {
      track.enabled = false
    }
  }

  unmute(): void {
    this.user?.unmute()
    for (const track of this.localStream?.getAudioTracks() ?? []) {
      track.enabled = true
    }
  }

  getRemoteMediaStream(): MediaStream | undefined {
    return this.user?.remoteMediaStream
  }

  getLocalMediaStream(): MediaStream | undefined {
    return this.localStream ?? this.user?.localMediaStream
  }

  async disconnect(): Promise<void> {
    if (!this.user) {
      this.stopLocalMic()
      return
    }
    const user = this.user
    this.user = null
    try {
      await user.unregister()
    } finally {
      await user.disconnect()
      this.stopLocalMic()
      this.events.onStatus?.('idle')
    }
  }

  /** Acquire or reuse a real microphone stream. Throws if none available. */
  async ensureLocalMic(): Promise<MediaStream> {
    if (this.localStream && hasLiveAudio(this.localStream)) {
      return this.localStream
    }
    this.stopLocalMic()
    try {
      this.localStream = await acquireMicrophoneStream()
      return this.localStream
    } catch (err) {
      throw new Error(formatCallError(err))
    }
  }

  private stopLocalMic(): void {
    if (!this.localStream) return
    for (const track of this.localStream.getTracks()) {
      track.stop()
    }
    this.localStream = null
  }
}

function hasLiveAudio(stream: MediaStream): boolean {
  return stream.getAudioTracks().some((t) => t.readyState === 'live')
}

function sipDomain(uri: string): string {
  const atIndex = uri.indexOf('@')
  return atIndex >= 0 ? uri.slice(atIndex + 1) : uri.replace(/^sip:/, '')
}

function normalizeDialNumber(value: string): string {
  return value.trim().replace(/[^\d+#*]/g, '')
}

function isDomMediaError(err: unknown, names: string[]): boolean {
  if (!(err instanceof DOMException)) return false
  return names.includes(err.name)
}

export function formatCallError(err: unknown): string {
  if (isDomMediaError(err, ['NotFoundError', 'DevicesNotFoundError'])) {
    return (
      'Микрофон не найден. Windows → Система → Звук → Ввод: выберите устройство; ' +
      'Параметры → Конфиденциальность → Микрофон — разрешите Chrome. Звонок без микрофона не начинается.'
    )
  }
  if (isDomMediaError(err, ['NotAllowedError', 'PermissionDeniedError'])) {
    return 'Нет доступа к микрофону. Замок у адреса сайта → Микрофон → Разрешить, затем Подключить линию снова.'
  }
  if (isDomMediaError(err, ['NotReadableError', 'AbortError'])) {
    return 'Микрофон занят другим приложением (Zoom/Teams/Discord). Закройте их и повторите.'
  }
  if (isDomMediaError(err, ['OverconstrainedError', 'ConstraintNotSatisfiedError'])) {
    return 'Браузер не смог открыть выбранный микрофон. Смените устройство ввода по умолчанию в Windows и обновите страницу.'
  }

  const raw = err instanceof Error ? err.message : String(err ?? '')
  const text = raw.toLowerCase()

  // Chrome sometimes wraps NotFound as plain Error with this text.
  if (text.includes('requested device not found') || text.includes('could not start audio source')) {
    return (
      'Микрофон не найден или недоступен (Requested device not found). ' +
      'Проверьте устройство ввода в Windows и что Chrome видит микрофон на chrome://settings/content/microphone. ' +
      'Звонок без микрофона не начинается.'
    )
  }

  if (
    text.includes('user not registered') ||
    text.includes('temporarily unavailable') ||
    text.includes('403') ||
    text.includes('404') ||
    text.includes('486') ||
    text.includes('503')
  ) {
    return `Ошибка SIP/Bitcall: ${raw}. Линия должна быть «Готово»; проверьте транк Bitcall.`
  }

  return raw || 'Не удалось начать звонок'
}

/** @deprecated use formatCallError */
export function mapMediaError(err: unknown): string {
  return formatCallError(err)
}

/**
 * Robust mic open: plain constraints → per-device ideal → minimal processing.
 * Never returns a fake/silent stream.
 */
async function acquireMicrophoneStream(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new DOMException(
      'getUserMedia недоступен (нужен HTTPS и современный Chrome)',
      'NotFoundError',
    )
  }

  const attempts: MediaStreamConstraints[] = [{ audio: true, video: false }]

  // After a permission prompt (or prior grant), deviceIds are readable.
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    for (const device of devices) {
      if (device.kind !== 'audioinput') continue
      if (device.deviceId) {
        attempts.push({
          audio: { deviceId: { ideal: device.deviceId } },
          video: false,
        })
      }
    }
  } catch {
    /* enumerate optional */
  }

  attempts.push({
    audio: {
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    },
    video: false,
  })

  let lastError: unknown = null
  for (const constraints of attempts) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      if (hasLiveAudio(stream)) {
        return stream
      }
      for (const track of stream.getTracks()) track.stop()
      lastError = new DOMException('Requested device not found', 'NotFoundError')
    } catch (err) {
      lastError = err
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new DOMException('Requested device not found', 'NotFoundError')
}
