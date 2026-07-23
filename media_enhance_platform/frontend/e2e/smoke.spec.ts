import { expect, test } from '@playwright/test'

test('public product, pricing and legal pages remain readable', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('让每一帧')
  await expect(page.getByText('图片高清', { exact: true }).first()).toBeVisible()

  await page.getByRole('button', { name: /EN/ }).click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Bring every frame')

  await page.goto('/pricing')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Pay only')
  await expect(page.getByText('1500', { exact: true })).toBeVisible()

  await page.goto('/legal/privacy')
  await expect(page.getByText('Pending before launch')).toBeVisible()
})

test('unauthenticated admin route is guarded', async ({ page }) => {
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/login\?next=\/admin$/)
})

test('register, upload and no-worker queue flow @desktop', async ({ page }) => {
  await page.goto('/register')
  const email = `playwright-${Date.now()}@example.com`
  await page.getByLabel('邮箱').fill(email)
  await page.getByLabel('密码').fill('playwright-password-123')
  await page.getByRole('button', { name: /注册/ }).click()
  await expect(page).toHaveURL(/\/workspace$/)

  await page.locator('input[type=file]').setInputFiles({
    name: 'tiny.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACAQMAAABIeJ9nAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAGUExURYuk/////4oMRGEAAAABYktHRAH/Ai3eAAAAB3RJTUUH6gcXFAAoKn+CJAAAAAxJREFUCNdjYGBgAAAABAABJzQnCgAAAABJRU5ErkJggg==',
      'base64',
    ),
  })
  await page.locator('.composer-card').first().getByRole('button', { name: '上传素材' }).click()
  await expect(page.locator('.selected-file')).toContainText('tiny.png')
  await page.locator('select').selectOption('4')
  await expect(page.locator('.quote-row')).toContainText('4 点')
  await page.getByRole('button', { name: '提交任务' }).click()
  await expect(page.getByText('等待算力接入')).toBeVisible()
  await expect(page.locator('.balance-card')).toContainText('96')
})

test('configured administrator can open operations console @desktop', async ({ page }) => {
  const email = process.env.CLARITY_E2E_ADMIN_EMAIL || 'admin@example.com'
  const password =
    process.env.CLARITY_E2E_ADMIN_PASSWORD || 'CHANGE_ME_ADMIN_PASSWORD'
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(email)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/workspace$/)
  await page.goto('/admin')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('运营后台')
  await expect(page.getByText('任务管理', { exact: true })).toBeVisible()
})
