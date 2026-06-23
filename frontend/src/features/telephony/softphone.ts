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
    const destination = `sip:${normalizeDialNumber(number)}@${this.accountDomain}`
    this.events.onStatus?.('calling')
    await this.user.call(destination)
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
