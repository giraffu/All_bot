import { mergeConfig, defineConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      include: ['src/**/*.test.ts'],
      exclude: [
        'node_modules/**',
        'src/stores/taskResultState.test.ts',
        'src/stores/tasksRuntime.test.ts'
      ]
    }
  })
)
