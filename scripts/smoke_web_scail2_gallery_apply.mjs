#!/usr/bin/env node

import fs from 'node:fs/promises'
import path from 'node:path'

const TASK_TYPES = [
  'scail2_action_transfer',
  'scail2_video_replacement',
  'scail2_face_swap_v2',
]
const DEFAULT_WEB_BASE_URL = 'https://web-test.aivison.it.com'
const DEFAULT_TIMEOUT_MS = 18 * 60 * 1000
const POLL_INTERVAL_MS = 5000

const env = process.env

const webBaseUrl = (env.CLOUD_TEST_WEB_BASE_URL || DEFAULT_WEB_BASE_URL).replace(/\/$/, '')
const apiBaseUrl = (env.CLOUD_TEST_API_BASE_URL || `${webBaseUrl}/api`).replace(/\/$/, '')
const authorToken = env.CLOUD_TEST_WEB_USER_A_TOKEN
const consumerToken = env.CLOUD_TEST_WEB_USER_B_TOKEN
const timeoutMs = Number(env.SCAIL2_SMOKE_TIMEOUT_MS || DEFAULT_TIMEOUT_MS)
const screenshotDir = env.SCAIL2_SMOKE_SCREENSHOT_DIR || '/tmp'
const reportDir = env.SCAIL2_SMOKE_REPORT_DIR || 'logs'

const fixtureConfig = {
  authorReferencePath: env.SCAIL2_SMOKE_AUTHOR_REFERENCE_IMAGE,
  consumerReferencePath: env.SCAIL2_SMOKE_CONSUMER_REFERENCE_IMAGE,
  motionVideoPath: env.SCAIL2_SMOKE_MOTION_VIDEO,
  authorReferenceKey: env.SCAIL2_SMOKE_AUTHOR_REFERENCE_KEY,
  consumerReferenceKey: env.SCAIL2_SMOKE_CONSUMER_REFERENCE_KEY,
  motionVideoKey: env.SCAIL2_SMOKE_MOTION_VIDEO_KEY,
}

const requireEnv = (name, value) => {
  if (!value) {
    throw new Error(`Missing required env: ${name}`)
  }
}

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

const sanitizeUrl = (value) => {
  if (!value || typeof value !== 'string') return value
  try {
    const url = new URL(value)
    url.search = ''
    return url.toString()
  } catch {
    return value.replace(/\?.*$/, '')
  }
}

const contentTypeFor = (filePath) => {
  const ext = path.extname(filePath).toLowerCase()
  if (ext === '.png') return 'image/png'
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg'
  if (ext === '.webp') return 'image/webp'
  if (ext === '.mov') return 'video/quicktime'
  if (ext === '.webm') return 'video/webm'
  return ext === '.mp4' ? 'video/mp4' : 'application/octet-stream'
}

const isVideoObjectKey = (value) => (
  typeof value === 'string' && /\.(mp4|mov|webm)(?:$|\?)/i.test(value)
)

const apiFetch = async (token, endpoint, options = {}) => {
  const headers = {
    Authorization: `Bearer ${token}`,
    ...(options.headers || {}),
  }
  let body = options.body
  if (body && typeof body === 'object' && !Buffer.isBuffer(body)) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(body)
  }

  const response = await fetch(`${apiBaseUrl}${endpoint}`, {
    ...options,
    headers,
    body,
  })
  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!response.ok) {
    throw new Error(`API ${endpoint} failed with ${response.status}: ${JSON.stringify(data)}`)
  }
  return data
}

const getCurrentUser = async (token) => apiFetch(token, '/users/me')

const uploadFixture = async (token, filePath) => {
  const absolutePath = path.resolve(filePath)
  const filename = path.basename(absolutePath)
  const contentType = contentTypeFor(absolutePath)
  const params = new URLSearchParams({ filename, content_type: contentType })
  const presigned = await apiFetch(token, `/storage/presigned-url?${params.toString()}`)
  const bytes = await fs.readFile(absolutePath)
  const uploadResponse = await fetch(presigned.upload_url, {
    method: 'PUT',
    headers: {
      'Content-Type': contentType,
    },
    body: bytes,
  })
  if (!uploadResponse.ok) {
    throw new Error(`Direct fixture upload failed with ${uploadResponse.status} for ${filename}`)
  }
  return presigned.object_key
}

const resolveFixtureKeys = async () => {
  if (
    fixtureConfig.authorReferenceKey
    && fixtureConfig.consumerReferenceKey
    && fixtureConfig.motionVideoKey
  ) {
    return {
      authorReferenceKey: fixtureConfig.authorReferenceKey,
      consumerReferenceKey: fixtureConfig.consumerReferenceKey,
      motionVideoKey: fixtureConfig.motionVideoKey,
    }
  }

  requireEnv('SCAIL2_SMOKE_AUTHOR_REFERENCE_IMAGE', fixtureConfig.authorReferencePath)
  requireEnv('SCAIL2_SMOKE_CONSUMER_REFERENCE_IMAGE', fixtureConfig.consumerReferencePath)
  requireEnv('SCAIL2_SMOKE_MOTION_VIDEO', fixtureConfig.motionVideoPath)

  return {
    authorReferenceKey: await uploadFixture(authorToken, fixtureConfig.authorReferencePath),
    consumerReferenceKey: await uploadFixture(consumerToken, fixtureConfig.consumerReferencePath),
    motionVideoKey: await uploadFixture(authorToken, fixtureConfig.motionVideoPath),
  }
}

const submitScail2Task = async ({
  token,
  taskType,
  referenceKey,
  motionVideoKey,
  prompt,
  negativePrompt = 'low quality, blur',
  sourcePostId = null,
}) => {
  const payload = {
    task_type: taskType,
    inputs: {
      images: [referenceKey, motionVideoKey],
      prompt,
      negative_prompt: negativePrompt,
      duration: 5,
    },
    priority: 0,
    is_template: sourcePostId != null,
  }
  if (sourcePostId != null) {
    payload.source_post_id = sourcePostId
  }
  return apiFetch(token, '/tasks/generate', {
    method: 'POST',
    body: payload,
  })
}

const pollTaskResult = async (token, taskId) => {
  const startedAt = Date.now()
  let lastPayload = null
  while (Date.now() - startedAt < timeoutMs) {
    lastPayload = await apiFetch(token, `/tasks/${encodeURIComponent(taskId)}/result`)
    if (['done', 'success'].includes(lastPayload.status) && lastPayload.result_url) {
      return lastPayload
    }
    if (['error', 'cancelled', 'failed'].includes(lastPayload.status)) {
      throw new Error(`Task ${taskId} finished with ${lastPayload.status}`)
    }
    await sleep(POLL_INTERVAL_MS)
  }
  throw new Error(`Timed out waiting for task ${taskId}; last status=${lastPayload?.status}`)
}

const submitToGallery = async (token, taskId) => apiFetch(
  token,
  `/gallery/posts/submit/${encodeURIComponent(taskId)}`,
  {
    method: 'POST',
    body: {},
  }
)

const findMyGalleryPost = async (token, taskType, taskId) => {
  const payload = await apiFetch(
    token,
    `/gallery/my-posts?page=1&size=20&task_type=${encodeURIComponent(taskType)}`
  )
  return (payload.items || []).find(item => item.task_id === taskId && item.is_active !== false)
}

const pollMyGalleryPost = async (token, taskType, taskId) => {
  const startedAt = Date.now()
  while (Date.now() - startedAt < 120000) {
    const post = await findMyGalleryPost(token, taskType, taskId)
    if (post) return post
    await sleep(3000)
  }
  throw new Error(`Timed out waiting for gallery post for task ${taskId}`)
}

const getApplyContext = async (token, postId) => apiFetch(
  token,
  `/gallery/posts/${encodeURIComponent(postId)}/apply-context`
)

const findHistory = async (token, taskId) => {
  const payload = await apiFetch(token, '/users/history')
  return (payload.items || []).find(item => item.task_id === taskId)
}

const pollAppliedCount = async (token, taskType, postId, minimum) => {
  const startedAt = Date.now()
  while (Date.now() - startedAt < 120000) {
    const payload = await apiFetch(
      token,
      `/gallery/posts?page=1&size=20&task_type=${encodeURIComponent(taskType)}&sort_by=latest&time_range=all`
    )
    const post = (payload.items || []).find(item => Number(item.id) === Number(postId))
    if (post && Number(post.applied_count || 0) >= minimum) {
      return post
    }
    await sleep(3000)
  }
  throw new Error(`Timed out waiting for applied_count >= ${minimum} on post ${postId}`)
}

const launchPlaywright = async () => {
  try {
    const { chromium } = await import('playwright')
    return chromium
  } catch (error) {
    throw new Error(
      'Playwright is not available. Run with: npx -y -p playwright node scripts/smoke_web_scail2_gallery_apply.mjs'
    )
  }
}

const captureTemplatePanel = async ({ token, user, postId, taskType, label, viewport }) => {
  if (env.SCAIL2_SMOKE_SKIP_BROWSER === '1') return null

  const chromium = await launchPlaywright()
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport })
  await context.addInitScript(({ tokenValue, userValue }) => {
    window.localStorage.setItem('token', tokenValue)
    window.localStorage.setItem('user', JSON.stringify(userValue))
  }, { tokenValue: token, userValue: user })

  const page = await context.newPage()
  const screenshotPath = path.join(
    screenshotDir,
    `scail2-${label}-${taskType}-${viewport.width}x${viewport.height}.png`
  )
  try {
    await page.goto(`${webBaseUrl}/gallery?task_type=${encodeURIComponent(taskType)}`, {
      waitUntil: 'networkidle',
      timeout: 45000,
    })
    await page.locator('.gallery-media-card').first().click({ timeout: 20000 })
    const applyButton = page.getByRole('button', { name: /一键应用|应用|Apply|Use/i }).last()
    await applyButton.click({ timeout: 20000 })
    await page.waitForSelector('.template-panel', { timeout: 20000 })
    await page.screenshot({ path: screenshotPath, fullPage: true })
    return screenshotPath
  } catch (error) {
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {})
    return `${screenshotPath} (fallback; template panel selector was not confirmed for post ${postId})`
  } finally {
    await browser.close()
  }
}

const runTaskTypeSmoke = async ({ taskType, fixtureKeys, authorUser, consumerUser }) => {
  const authorPrompt = `cloud test scail2 template ${taskType}`
  const consumerPrompt = `cloud test scail2 apply ${taskType}`

  const authorTask = await submitScail2Task({
    token: authorToken,
    taskType,
    referenceKey: fixtureKeys.authorReferenceKey,
    motionVideoKey: fixtureKeys.motionVideoKey,
    prompt: authorPrompt,
  })
  const authorResult = await pollTaskResult(authorToken, authorTask.task_id)

  await submitToGallery(authorToken, authorTask.task_id)
  const post = await pollMyGalleryPost(authorToken, taskType, authorTask.task_id)
  const applyContext = await getApplyContext(consumerToken, post.id)
  const originalInputFiles = Array.isArray(post.input_files) ? post.input_files : []
  if (originalInputFiles.length < 2) {
    throw new Error(`Expected gallery post ${post.id} to expose reference and motion inputs for ${taskType}`)
  }
  if (applyContext.input_file !== originalInputFiles[1]) {
    throw new Error(`Expected apply-context input_file to reuse the second gallery input for ${taskType}`)
  }
  if (!isVideoObjectKey(applyContext.input_file)) {
    throw new Error(`Expected apply-context input_file to be a video object for ${taskType}`)
  }

  const screenshots = []
  screenshots.push(await captureTemplatePanel({
    token: consumerToken,
    user: consumerUser,
    postId: post.id,
    taskType,
    label: 'desktop-template',
    viewport: { width: 1440, height: 900 },
  }))
  screenshots.push(await captureTemplatePanel({
    token: consumerToken,
    user: consumerUser,
    postId: post.id,
    taskType,
    label: 'mobile-template',
    viewport: { width: 390, height: 844 },
  }))

  const consumerTask = await submitScail2Task({
    token: consumerToken,
    taskType,
    referenceKey: fixtureKeys.consumerReferenceKey,
    motionVideoKey: applyContext.input_file,
    prompt: consumerPrompt,
    negativePrompt: applyContext.negative_prompt || 'low quality, blur',
    sourcePostId: post.id,
  })
  const consumerResult = await pollTaskResult(consumerToken, consumerTask.task_id)
  const consumerHistory = await findHistory(consumerToken, consumerTask.task_id)
  if (!consumerHistory) {
    throw new Error(`Applied task ${consumerTask.task_id} was not found in consumer history`)
  }
  if (consumerHistory.allow_contribute !== false) {
    throw new Error(`Applied task ${consumerTask.task_id} should have allow_contribute=false`)
  }

  const postAfterApply = await pollAppliedCount(
    authorToken,
    taskType,
    post.id,
    Number(post.applied_count || 0) + 1
  )

  return {
    taskType,
    authorTaskId: authorTask.task_id,
    consumerTaskId: consumerTask.task_id,
    postId: post.id,
    appliedCount: postAfterApply.applied_count,
    authorResultUrl: sanitizeUrl(authorResult.result_url),
    consumerResultUrl: sanitizeUrl(consumerResult.result_url),
    screenshots: screenshots.filter(Boolean),
  }
}

const main = async () => {
  requireEnv('CLOUD_TEST_WEB_USER_A_TOKEN', authorToken)
  requireEnv('CLOUD_TEST_WEB_USER_B_TOKEN', consumerToken)

  const authorUser = await getCurrentUser(authorToken)
  const consumerUser = await getCurrentUser(consumerToken)
  const fixtureKeys = await resolveFixtureKeys()

  const results = []
  for (const taskType of TASK_TYPES) {
    results.push(await runTaskTypeSmoke({
      taskType,
      fixtureKeys,
      authorUser,
      consumerUser,
    }))
  }

  await fs.mkdir(reportDir, { recursive: true })
  const reportPath = path.join(
    reportDir,
    `scail2_gallery_apply_smoke_${new Date().toISOString().replace(/[:.]/g, '-')}.json`
  )
  await fs.writeFile(
    reportPath,
    JSON.stringify({
      webBaseUrl,
      apiBaseUrl,
      generatedAt: new Date().toISOString(),
      results,
    }, null, 2)
  )

  console.log(JSON.stringify({
    ok: true,
    reportPath,
    taskTypes: results.map(item => item.taskType),
    screenshots: results.flatMap(item => item.screenshots),
  }, null, 2))
}

main().catch((error) => {
  console.error(error.message)
  process.exitCode = 1
})
