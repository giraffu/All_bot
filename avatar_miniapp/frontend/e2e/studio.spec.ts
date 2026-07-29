import { expect, test } from '@playwright/test'

const character = {
  id: 'character-demo',
  name: 'Luna',
  description: 'Local fixture character',
  status: 'draft',
  source_object_key: 'allbot/web_uploads/1/demo.png',
  preview_url: null,
  latest_model: null,
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('avatar_miniapp_token', 'visual-test-token')
    localStorage.setItem(
      'avatar_miniapp_user',
      JSON.stringify({
        id: 1,
        username: 'studio_user',
        full_name: 'Studio User',
        language_code: 'zh',
        credits: 10,
        user_group: '练气期',
        current_identity: '内门弟子',
      }),
    )
  })
  await page.route('**/api/miniapp/characters', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([character]) }),
  )
})

test('renders the local build studio responsively', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '本地演示建模' })).toBeVisible()
  await expect(page.getByText('演示模型不会根据上传照片重建真人', { exact: false })).toBeVisible()
  await page.screenshot({
    path: `/tmp/avatar-studio-${testInfo.project.name}.png`,
    fullPage: true,
  })
})
