import type { ConfigEnv } from 'vite'
import { mergeConfig, defineConfig } from 'vitest/config'
import viteConfig from './vite.config'

const testConfigEnv: ConfigEnv = {
  command: 'serve',
  mode: 'test',
  isSsrBuild: false,
  isPreview: false,
}

const resolvedViteConfig =
  typeof viteConfig === 'function'
    ? viteConfig(testConfigEnv)
    : viteConfig

export default mergeConfig(
  resolvedViteConfig,
  defineConfig({
    test: {
      include: ['src/**/*.test.ts'],
      exclude: ['node_modules/**']
    }
  })
)
