export type RegisterFilters = Record<string, string | { min?: number | null; max?: number | null }>
export type RegisterQuery = { filters: RegisterFilters; sort: string | null; descending: boolean }
export const registerFields = [
  ['client','Клиент'], ['manager','Менеджер'], ['buyer','Лавка клиента'], ['supplier','Наша лавка'],
  ['inn','ИНН покупателя'], ['okved','ОКВЭД'], ['period','Период'], ['category','Категория'], ['comment','Комментарий'],
  ['volume','Объём, ₽'], ['due','К оплате, ₽'], ['paid','Оплачено, ₽'], ['debt','Долг, ₽'],
  ['ben','Цена бена, ₽'], ['margin','Маржа после начисления, ₽'], ['plan','Плановая маржа, ₽'], ['returned','Вернули бену, ₽'],
].map(([value,label])=>({value,label,numeric:['volume','due','paid','debt','ben','margin','plan','returned'].includes(value)}))
