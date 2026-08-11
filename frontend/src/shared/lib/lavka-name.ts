/** Полное юр.имя → короткое «ООО „АФИНА“». */
export function shortLavkaName(name: string | null | undefined): string {
  const raw = (name || '').trim()
  if (!raw) return ''
  const quoted = raw.match(/[«"“„]([^»"”]+)[»"”]/)
  if (quoted?.[1]?.trim()) {
    const inner = quoted[1].trim()
    if (/общество\s+с\s+ограниченной\s+ответственностью|ооо/i.test(raw)) {
      return `ООО «${inner}»`
    }
    return inner
  }
  return raw
    .replace(/Общество\s+с\s+ограниченной\s+ответственностью/gi, 'ООО')
    .replace(/\s+/g, ' ')
    .trim()
}

export function lavkaLabel(name: string | null | undefined, inn: string): string {
  const short = shortLavkaName(name)
  return short ? `${short} · ${inn}` : inn
}
