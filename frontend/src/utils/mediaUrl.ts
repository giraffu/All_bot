export const resolveMediaUrl = (path: string): string => {
  if (!path) {
    return ''
  }

  if (
    path.startsWith('https://')
    || path.startsWith('http://')
    || path.startsWith('blob:')
    || path.startsWith('data:')
  ) {
    return path
  }

  return ''
}
