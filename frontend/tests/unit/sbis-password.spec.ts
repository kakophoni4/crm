import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,expect,it,vi} from 'vitest'
import SbisPassword from '@/features/accounting/SbisPassword.vue'
const {auth,post,patch}=vi.hoisted(()=>({auth:{isAdmin:false,isAccountant:true,user:{id:7}},post:vi.fn(),patch:vi.fn()}))
vi.mock('@/shared/store/auth',()=>({useAuthStore:()=>auth}))
vi.mock('@/shared/api/http',()=>({http:{post,patch},AppError:class extends Error{}}))
vi.mock('naive-ui',async original=>({...await original<object>(),useMessage:()=>({success:vi.fn(),error:vi.fn()})}))
beforeEach(()=>{auth.isAdmin=false;post.mockReset();patch.mockReset()})
it('does not fetch on mount; reveals only on click and clears on hide',async()=>{
 const w=mount(SbisPassword,{props:{unitId:10,accountantId:7}})
 expect(w.text()).toContain('********');expect(post).not.toHaveBeenCalled()
 post.mockResolvedValue({data:{password:'example'}})
 await w.findAll('button').find(b=>b.text()==='Показать')!.trigger('click');await flushPromises()
 expect(post).toHaveBeenCalledWith('/accounting/units/10/sbis-password/reveal')
 expect((w.get('input').element as HTMLInputElement).value).toBe('example')
 await w.findAll('button').find(b=>b.text()==='Скрыть')!.trigger('click')
 expect(w.find('input').exists()).toBe(false);w.unmount()
})
it('hides controls from an unassigned accountant',()=>{
 const w=mount(SbisPassword,{props:{unitId:10,accountantId:8}})
 expect(w.find('button').exists()).toBe(false);expect(post).not.toHaveBeenCalled();w.unmount()
})
it('lets admin save a new password separately without fetching the existing one',async()=>{
 auth.isAdmin=true;patch.mockResolvedValue({data:{}})
 const w=mount(SbisPassword,{props:{unitId:10,accountantId:8}})
 await w.findAll('button').find(b=>b.text()==='Изменить')!.trigger('click')
 await w.get('input').setValue(' example ')
 await w.findAll('button').find(b=>b.text()==='Сохранить пароль')!.trigger('click');await flushPromises()
 expect(patch).toHaveBeenCalledWith('/accounting/units/10/card',{sbis_password:' example '})
 expect(post).not.toHaveBeenCalled();w.unmount()
})
