/**
 * Shared payment form rules for OPT orders.
 * Document confirmation is required for all methods except cash.
 */
export function paymentDocumentRequired(
  paymentType: 'card' | 'crypto' | 'wire' | 'cash' | string,
): boolean {
  return paymentType !== 'cash'
}

export function validateOptPaymentDocuments(input: {
  payment_type: 'card' | 'crypto' | 'wire' | 'cash' | string
  document_file_ids: number[]
}): string | null {
  if (paymentDocumentRequired(input.payment_type) && input.document_file_ids.length === 0) {
    return 'Прикрепите документ подтверждения оплаты (для наличных не требуется)'
  }
  return null
}
