#!/usr/bin/env node

import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'

const requireFromFrontend = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium } = requireFromFrontend('playwright')

const WEB_BASE = (process.env.ALLBOT_WEB_SMOKE_WEB_BASE || 'https://web-cf-test.aivison.it.com').replace(/\/$/, '')
const API_BASE = (process.env.ALLBOT_WEB_SMOKE_API_BASE || 'https://api-cf-test.aivison.it.com/api').replace(/\/$/, '')
const USERNAME = process.env.ALLBOT_WEB_SMOKE_USERNAME
const PASSWORD = process.env.ALLBOT_WEB_SMOKE_PASSWORD
const IMAGE_PATH = process.env.ALLBOT_WEB_SMOKE_IMAGE_PATH
const SCREENSHOT_DIR = process.env.ALLBOT_WEB_SMOKE_SCREENSHOT_DIR || '/tmp'
const TASK_TYPE = 'pornmaster_flux2_edit_bf16'
const GROUP_TYPE = 'free_edit_v3_group'
const POLL_MS = 5000
const TIMEOUT_MS = Number(process.env.ALLBOT_WEB_SMOKE_TIMEOUT_MS || 20 * 60 * 1000)

for (const [name, value] of Object.entries({
  ALLBOT_WEB_SMOKE_USERNAME: USERNAME,
  ALLBOT_WEB_SMOKE_PASSWORD: PASSWORD,
  ALLBOT_WEB_SMOKE_IMAGE_PATH: IMAGE_PATH,
})) {
  if (!value) throw new Error(`Missing required environment variable: ${name}`)
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

const request = async (endpoint, { token, method = 'GET', body, headers = {} } = {}) => {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body && !Buffer.isBuffer(body) ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body && !Buffer.isBuffer(body) ? JSON.stringify(body) : body,
  })
  const text = await response.text()
  let payload = null
  try { payload = text ? JSON.parse(text) : null } catch { payload = text }
  if (!response.ok) {
    throw new Error(`${method} ${endpoint} failed (${response.status}): ${JSON.stringify(payload)}`)
  }
  return payload
}

const contentType = filePath => {
  const ext = path.extname(filePath).toLowerCase()
  if (ext === '.png') return 'image/png'
  if (ext === '.webp') return 'image/webp'
  return 'image/jpeg'
}

const uploadImage = async token => {
  const absolutePath = path.resolve(IMAGE_PATH)
  const type = contentType(absolutePath)
  const params = new URLSearchParams({ filename: path.basename(absolutePath), content_type: type })
  const presigned = await request(`/storage/presigned-url?${params}`, { token })
  const upload = await fetch(presigned.upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': type },
    body: await fs.readFile(absolutePath),
  })
  if (!upload.ok) throw new Error(`Fixture upload failed (${upload.status})`)
  return presigned.object_key
}

const submitTask = (token, imageKey, prompt, sourcePostId = null) => request('/tasks/generate', {
  token,
  method: 'POST',
  body: {
    task_type: TASK_TYPE,
    inputs: { images: [imageKey] },
    prompt,
    priority: 0,
    is_template: sourcePostId !== null,
    ...(sourcePostId !== null ? { source_post_id: sourcePostId } : {}),
  },
})

const poll = async (label, load, done) => {
  const started = Date.now()
  let latest = null
  while (Date.now() - started < TIMEOUT_MS) {
    latest = await load()
    if (done(latest)) return latest
    if (['error', 'failed', 'cancelled'].includes(latest?.status)) {
      throw new Error(`${label} failed with status ${latest.status}`)
    }
    await sleep(POLL_MS)
  }
  throw new Error(`${label} timed out; last payload=${JSON.stringify(latest)}`)
}

const pollTask = (token, taskId) => poll(
  `task ${taskId}`,
  () => request(`/tasks/${encodeURIComponent(taskId)}/result`, { token }),
  value => ['done', 'success'].includes(value?.status) && Boolean(value?.result_url),
)

const findHistory = async (token, taskId) => {
  const payload = await request('/users/history', { token })
  const items = Array.isArray(payload) ? payload : (payload?.items || [])
  return items.find(item => item.task_id === taskId) || null
}

const pollPost = (token, taskId) => poll(
  'gallery post',
  async () => {
    const payload = await request(`/gallery/my-posts?page=1&size=20&task_type=${GROUP_TYPE}`, { token })
    return (payload?.items || []).find(item => item.task_id === taskId && item.is_active !== false) || {}
  },
  value => Boolean(value?.id),
)

const installAuth = async (context, token, user) => {
  await context.addInitScript(({ tokenValue, userValue }) => {
    localStorage.setItem('token', tokenValue)
    localStorage.setItem('user', JSON.stringify(userValue))
  }, { tokenValue: token, userValue: user })
}

const captureLab = async (browser, token, user, viewport, suffix) => {
  const context = await browser.newContext({ viewport })
  await installAuth(context, token, user)
  const page = await context.newPage()
  const output = path.join(SCREENSHOT_DIR, `web-free-edit-v3-lab-${suffix}.png`)
  await page.goto(`${WEB_BASE}/custom-features`, { waitUntil: 'networkidle', timeout: 60000 })
  await page.getByText(/自由P图 v3|Free Edit v3/, { exact: true }).click({ timeout: 30000 })
  await page.getByText(/自动恢复原图人脸|restore the original face/i).waitFor({ timeout: 30000 })
  await page.screenshot({ path: output, fullPage: true })
  await context.close()
  return output
}

const captureApplyPanel = async (browser, token, user) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  await installAuth(context, token, user)
  const page = await context.newPage()
  const output = path.join(SCREENSHOT_DIR, 'web-free-edit-v3-gallery-apply.png')
  await page.goto(`${WEB_BASE}/gallery?task_type=${GROUP_TYPE}`, { waitUntil: 'networkidle', timeout: 60000 })
  await page.locator('.gallery-media-card').first().click({ timeout: 30000 })
  await page.getByRole('button', { name: /一键应用|应用|Apply|Use/i }).last().click({ timeout: 30000 })
  await page.locator('.template-panel').waitFor({ timeout: 30000 })
  await page.screenshot({ path: output, fullPage: true })
  await context.close()
  return output
}

let postId = null
const report = { task_type: TASK_TYPE, group_type: GROUP_TYPE, screenshots: [] }

try {
  const login = await request('/auth/login', {
    method: 'POST',
    body: { username: USERNAME, password: PASSWORD },
  })
  const token = login.access_token
  const user = login.user
  if (!token || !user) throw new Error('Login response did not include token and user')
  if (Number(user.credits || 0) < 10) throw new Error('Smoke account requires at least 10 credits')

  const imageKey = await uploadImage(token)
  const prompt = `web free edit v3 smoke ${new Date().toISOString()}`
  const generated = await submitTask(token, imageKey, prompt)
  if (generated.cost !== 5) throw new Error(`Expected v3 cost 5, got ${generated.cost}`)
  await pollTask(token, generated.task_id)

  const generatedHistory = await poll(
    'generated history',
    () => findHistory(token, generated.task_id),
    value => Boolean(value),
  )
  if (generatedHistory.type !== TASK_TYPE || generatedHistory.allow_contribute === false) {
    throw new Error('Generated history does not expose the expected v3 contribution contract')
  }

  await request(`/gallery/posts/submit/${encodeURIComponent(generated.task_id)}`, {
    token,
    method: 'POST',
    body: {},
  })
  const post = await pollPost(token, generated.task_id)
  postId = post.id
  const applyContext = await request(`/gallery/posts/${postId}/apply-context`, { token })
  if (applyContext.prompt !== prompt || applyContext.task_type !== TASK_TYPE) {
    throw new Error('Gallery apply-context did not preserve the v3 prompt and type')
  }

  const browser = await chromium.launch({ headless: true })
  try {
    report.screenshots.push(
      await captureLab(browser, token, user, { width: 1440, height: 1000 }, 'desktop'),
      await captureLab(browser, token, user, { width: 390, height: 844 }, 'mobile'),
      await captureApplyPanel(browser, token, user),
    )
  } finally {
    await browser.close()
  }

  const applied = await submitTask(token, imageKey, applyContext.prompt, postId)
  if (applied.cost !== 5) throw new Error(`Expected applied v3 cost 5, got ${applied.cost}`)
  await pollTask(token, applied.task_id)
  const appliedHistory = await poll(
    'applied history',
    () => findHistory(token, applied.task_id),
    value => Boolean(value),
  )
  if (appliedHistory.type !== TASK_TYPE || appliedHistory.allow_contribute !== false) {
    throw new Error('Applied history must be v3 and non-contributable')
  }

  const appliedPost = await poll(
    'gallery applied_count',
    async () => {
      const payload = await request(`/gallery/posts?page=1&size=20&task_type=${GROUP_TYPE}&sort_by=latest&time_range=all`, { token })
      return (payload?.items || []).find(item => Number(item.id) === Number(postId)) || {}
    },
    value => Number(value?.applied_count || 0) >= 1,
  )

  Object.assign(report, {
    generated_task_id: generated.task_id,
    applied_task_id: applied.task_id,
    gallery_post_id: postId,
    applied_count: appliedPost.applied_count,
    generated_allow_contribute: generatedHistory.allow_contribute,
    applied_allow_contribute: appliedHistory.allow_contribute,
  })
  console.log(JSON.stringify(report, null, 2))
} finally {
  if (postId) {
    try {
      const login = await request('/auth/login', {
        method: 'POST',
        body: { username: USERNAME, password: PASSWORD },
      })
      await request(`/gallery/posts/${postId}`, { token: login.access_token, method: 'DELETE' })
    } catch (error) {
      console.error(`Gallery cleanup failed for post ${postId}: ${error.message}`)
    }
  }
}
