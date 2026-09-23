import {mount,flushPromises} from '@vue/test-utils'
import {describe,it,expect,vi} from 'vitest'
import VoiceTranscript from '@/widgets/chat/VoiceTranscript.vue'
import {formatChatMessagePreview} from '@/features/chats/message-preview'
const {post,get}=vi.hoisted(()=>({post:vi.fn(),get:vi.fn()}))
vi.mock('@/shared/api/http',()=>({http:{post,get}}))
describe('voice transcript',()=>{
 it('labels legacy generated filenames without replacing captions',()=>{
  expect(formatChatMessagePreview('file_1695.oga')).toBe('Голосовое сообщение')
  expect(formatChatMessagePreview('Посмотри file_1695.oga')).toBe('Посмотри file_1695.oga')
 })
 it('requests text only on click and reuses it',async()=>{
  post.mockResolvedValue({data:{status:'ready',text:'Здравствуйте'}})
  const w=mount(VoiceTranscript,{props:{path:'chats/1/messages/2/attachments/0'}})
  expect(post).not.toHaveBeenCalled()
  await w.find('button').trigger('click');await flushPromises()
  expect(w.text()).toContain('Здравствуйте')
  await w.find('button').trigger('click');expect(w.find('.voice-transcript__text').exists()).toBe(false)
  await w.find('button').trigger('click');expect(post).toHaveBeenCalledTimes(1)
  w.unmount()
 })
 it('shows saved text without a request',async()=>{
  post.mockClear()
  const w=mount(VoiceTranscript,{props:{path:'chats/1/messages/2/attachments/0',initial:'Сохранено'}})
  await w.find('button').trigger('click');expect(w.text()).toContain('Сохранено');expect(post).not.toHaveBeenCalled();w.unmount()
 })
})
