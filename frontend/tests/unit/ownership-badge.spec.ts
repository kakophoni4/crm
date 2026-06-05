import { mount } from '@vue/test-utils'

import { NConfigProvider } from 'naive-ui'

import { describe, expect, it } from 'vitest'

import { defineComponent, h } from 'vue'



import ContactOwnerBadge from '@/entities/contact/ContactOwnerBadge.vue'



function mountBadge(props: Record<string, unknown>) {

  const Host = defineComponent({

    setup() {

      return () => h(NConfigProvider, null, () => h(ContactOwnerBadge, props))

    },

  })

  return mount(Host)

}



describe('ContactOwnerBadge', () => {

  it('shows owner full name', () => {

    const wrapper = mountBadge({ ownerFullName: 'Аня' })

    expect(wrapper.text()).toContain('Владелец: Аня')

    wrapper.unmount()

  })



  it('falls back to user id', () => {

    const wrapper = mountBadge({ ownerUserId: 42 })

    expect(wrapper.text()).toContain('Владелец: #42')

    wrapper.unmount()

  })



  it('shows unassigned label', () => {

    const wrapper = mountBadge({})

    expect(wrapper.text()).toContain('Владелец: Не назначен')

    wrapper.unmount()

  })

})


