/** Keep the ten most recent server receipts, without changing fill information. */
export function appendReceipt<T extends { order_id: string }>(
  previous: readonly T[], response: T
): T[] {
  return [response, ...previous.filter(receipt => receipt.order_id !== response.order_id)].slice(0, 10);
}
