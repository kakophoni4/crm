/** Label for outbound messages sent by a colleague on behalf of the card owner. */



export interface OnBehalfFields {

  is_on_behalf?: boolean

  author_full_name?: string | null

  card_owner_full_name?: string | null

  author_user_id?: number | null

  card_owner_user_id?: number | null

}



export function formatOnBehalfLabel(fields: OnBehalfFields): string | null {

  if (!fields.is_on_behalf) return null



  const author =

    fields.author_full_name?.trim() ||

    (fields.author_user_id != null ? `#${fields.author_user_id}` : 'Оператор')

  const owner =

    fields.card_owner_full_name?.trim() ||

    (fields.card_owner_user_id != null ? `#${fields.card_owner_user_id}` : 'владелец')



  return `Ответил ${author} (карточка: ${owner})`

}


