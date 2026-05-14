import test from 'node:test'
import assert from 'node:assert/strict'

import {
  canLockTemplateVideoPromptControls,
  getTemplateVideoSettings,
  toPositiveInteger
} from './templateVideoSettings.ts'

test('toPositiveInteger rejects nullish and non-positive values', () => {
  assert.equal(toPositiveInteger(null), null)
  assert.equal(toPositiveInteger(undefined), null)
  assert.equal(toPositiveInteger(''), null)
  assert.equal(toPositiveInteger('   '), null)
  assert.equal(toPositiveInteger(0), null)
  assert.equal(toPositiveInteger('0'), null)
  assert.equal(toPositiveInteger(-1), null)
  assert.equal(toPositiveInteger('abc'), null)
})

test('getTemplateVideoSettings rejects incomplete template values', () => {
  assert.equal(getTemplateVideoSettings({ width: null, duration: null }), null)
  assert.equal(getTemplateVideoSettings({ width: 1024, duration: null }), null)
  assert.equal(
    getTemplateVideoSettings({ width: 1280, height: null, duration: 10 }, true),
    null
  )
})

test('getTemplateVideoSettings normalizes valid template values', () => {
  assert.deepEqual(
    getTemplateVideoSettings({ width: '1024', duration: '8' }),
    {
      width: 1024,
      height: null,
      duration: 8
    }
  )
  assert.deepEqual(
    getTemplateVideoSettings({ width: '1280', height: '704', duration: '10' }, true),
    {
      width: 1280,
      height: 704,
      duration: 10
    }
  )
})

test('template video prompt controls stay editable when template prompt config is incomplete', () => {
  assert.equal(
    canLockTemplateVideoPromptControls({ prompt: 'cinematic motion blur' }, 'custom_video'),
    true
  )
  assert.equal(
    canLockTemplateVideoPromptControls({ prompt: 'cinematic motion blur' }, 'ltx_video'),
    true
  )
  assert.equal(
    canLockTemplateVideoPromptControls({ prompt: 'cinematic motion blur' }, 'video_lora'),
    false
  )
  assert.equal(
    canLockTemplateVideoPromptControls(
      { prompt: 'cinematic motion blur', lora_name: 'BreastGrow' },
      'video_lora'
    ),
    true
  )
  assert.equal(
    canLockTemplateVideoPromptControls({ prompt: '   ', lora_name: 'BreastGrow' }, 'video_lora'),
    false
  )
})
