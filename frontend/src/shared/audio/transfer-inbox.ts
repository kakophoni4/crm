let audioContext: AudioContext | null = null

function getAudioContext(): AudioContext {
  if (!audioContext) {
    audioContext = new AudioContext()
  }
  return audioContext
}

/** Notification tone for inbox / activity WS events — two gentle notes, ~0.55s. */
export async function playTransferInboxSound(): Promise<void> {
  try {
    const ctx = getAudioContext()
    if (ctx.state === 'suspended') {
      await ctx.resume()
    }

    const now = ctx.currentTime
    const duration = 0.55

    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(587, now)
    osc.frequency.linearRampToValueAtTime(784, now + duration * 0.45)
    gain.gain.setValueAtTime(0.0001, now)
    gain.gain.linearRampToValueAtTime(0.09, now + 0.04)
    gain.gain.setValueAtTime(0.09, now + duration * 0.35)
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(now)
    osc.stop(now + duration + 0.05)
  } catch {
    /* ignore autoplay / unsupported */
  }
}
