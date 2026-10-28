export function readApiPayload(text, contentType) {
  const type = String(contentType || '')
  if (!type.includes('application/json') && !type.includes('+json')) {
    throw new Error('The server returned a non-JSON response. It may be restarting.')
  }
  return text ? JSON.parse(text) : null
}
