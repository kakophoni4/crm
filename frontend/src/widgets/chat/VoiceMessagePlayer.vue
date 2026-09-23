<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Play, Pause, LoaderCircle, RotateCcw } from 'lucide-vue-next'
const props = defineProps<{ src: string | null; blob: Blob | null; loading: boolean; failed: boolean }>()
const emit = defineEmits<{ load: [] }>()
const audio = ref<HTMLAudioElement | null>(null)
const playing = ref(false), requested = ref(false), mediaFailed = ref(false)
const time = ref(0), duration = ref(0), speed = ref(1)
const peaks = ref<number[]>(Array(44).fill(0.15))
const progress = computed(() => duration.value > 0 ? time.value / duration.value : 0)
const format = (n: number) => `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, '0')}`
let generation = 0
async function start() {
 await nextTick()
 try { await audio.value?.play() } catch { mediaFailed.value = true; requested.value = false }
}
function toggle() {
 if (props.loading) return
 if (playing.value) { audio.value?.pause(); return }
 mediaFailed.value = false
 if (!props.src) { requested.value = true; emit('load') } else { if(audio.value?.error) audio.value.load(); void start() }
}
function metadata() { if(audio.value) audio.value.playbackRate=speed.value; const d=audio.value?.duration; if(d && Number.isFinite(d)) duration.value=d }
function seek(event: Event) { if(audio.value && duration.value) { audio.value.currentTime=Number((event.target as HTMLInputElement).value); time.value=audio.value.currentTime } }
function changeSpeed() { speed.value=speed.value===1?1.5:speed.value===1.5?2:1; if(audio.value) audio.value.playbackRate=speed.value }
function stopOther(event: Event) { if(event.target!==audio.value && event.target instanceof HTMLMediaElement) audio.value?.pause() }
// One voice message at a time, including players in other message bubbles.
document.addEventListener('play',stopOther,true)
watch(()=>props.src,()=>{playing.value=false;time.value=0;mediaFailed.value=false;if(props.src && requested.value) void start()})
watch(()=>props.failed,v=>{if(v) requested.value=false})
watch(()=>props.blob,async blob=>{
 const token=++generation
 peaks.value=Array(44).fill(0.15);duration.value=0
 if(!blob || blob.size>20*1024*1024) return
 let context: AudioContext | undefined
 try {
  context=new AudioContext()
  const buffer=await context.decodeAudioData(await blob.arrayBuffer())
  if(token!==generation)return
  duration.value=buffer.duration
  const data=buffer.getChannelData(0), step=Math.max(1,Math.floor(data.length/44))
  const values=Array.from({length:44},(_,i)=>{let max=0;for(let j=i*step;j<Math.min((i+1)*step,data.length);j++)max=Math.max(max,Math.abs(data[j]));return max})
  const max=Math.max(...values,0.01);peaks.value=values.map(v=>Math.max(0.12,v/max))
 } catch { /* Playback can still work when waveform decoding is unsupported. */ }
 finally {if(context) await context.close().catch(()=>{})}
},{immediate:true})
onBeforeUnmount(()=>{generation++;audio.value?.pause();document.removeEventListener('play',stopOther,true)})
</script>
<template>
 <div class="voice-player">
  <audio v-if="src" ref="audio" :src="src" preload="metadata" @loadedmetadata="metadata" @durationchange="metadata" @timeupdate="time=audio?.currentTime || 0" @play="playing=true;requested=false" @pause="playing=false" @ended="playing=false;time=0" @error="mediaFailed=true;playing=false" />
  <button class="voice-play" :disabled="loading" :aria-label="loading?'Загрузка голосового':playing?'Пауза':failed||mediaFailed?'Повторить воспроизведение':'Воспроизвести голосовое'" @click="toggle"><LoaderCircle v-if="loading" class="voice-spinner" :size="20"/><Pause v-else-if="playing" :size="20"/><RotateCcw v-else-if="failed||mediaFailed" :size="20"/><Play v-else :size="20" fill="currentColor"/></button>
  <div class="voice-track">
   <div class="voice-wave">
    <svg viewBox="0 0 220 32" preserveAspectRatio="none" aria-hidden="true"><rect v-for="(peak,i) in peaks" :key="i" :x="i*5" :y="16-peak*14" width="3" :height="peak*28" rx="1.5" :class="{played:(i+1)/peaks.length<=progress}"/></svg>
    <input type="range" min="0" :max="duration || 1" step="0.1" :value="time" :disabled="!src || !duration" aria-label="Перемотка голосового" :aria-valuetext="format(time)" @input="seek" />
   </div>
   <div class="voice-meta"><span>{{ loading?'Загрузка…':failed?'Не удалось загрузить':mediaFailed?'Не удалось воспроизвести':`${format(time)} / ${format(duration)}` }}</span><button :aria-label="`Скорость воспроизведения ${speed}`" @click="changeSpeed">{{ speed }}×</button></div>
  </div>
 </div>
</template>
<style scoped>
.voice-player{display:flex;align-items:center;gap:10px;width:280px;max-width:100%;padding:4px 0;color:var(--app-text)}
.voice-play{width:42px;height:42px;flex-shrink:0;display:grid;place-items:center;border:0;border-radius:50%;background:var(--app-accent);color:var(--app-surface);cursor:pointer}
.voice-play:disabled{cursor:wait}.voice-track{min-width:0;flex:1}.voice-wave{position:relative;height:32px}.voice-wave svg{width:100%;height:100%;fill:color-mix(in srgb,var(--app-accent) 35%,var(--app-surface))}.voice-wave .played{fill:var(--app-accent)}
.voice-wave input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer}.voice-wave:focus-within{outline:2px solid var(--app-accent);outline-offset:2px;border-radius:4px}
.voice-meta{display:flex;justify-content:space-between;align-items:center;color:var(--app-text-muted);font-size:11px;font-variant-numeric:tabular-nums;gap:6px}
.voice-meta button{border:0;border-radius:8px;background:color-mix(in srgb,var(--app-accent) 12%,transparent);color:var(--app-accent);font:inherit;font-weight:600;padding:1px 7px;cursor:pointer}
.voice-spinner{animation:voice-spin 1s linear infinite}@keyframes voice-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.voice-spinner{animation:none}}
</style>
