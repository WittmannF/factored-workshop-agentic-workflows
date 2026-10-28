import assert from 'node:assert/strict'
import test from 'node:test'
import { readApiPayload } from './api.js'

test('a gateway error page is reported as a restart', () => {
  assert.throws(
    () => readApiPayload('<!DOCTYPE html><html>', 'text/html'),
    /restarting/,
  )
})

test('a JSON error body stays available to the caller', () => {
  const payload = readApiPayload('{"detail":"Unknown case"}', 'application/json')
  assert.equal(payload.detail, 'Unknown case')
})
