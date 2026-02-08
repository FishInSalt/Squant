import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: 'happy-dom',
      include: ['src/**/*.{test,spec}.ts'],
      exclude: ['node_modules', 'dist'],
      setupFiles: ['./src/__tests__/setup.ts'],
      css: false,
      server: {
        deps: {
          inline: ['element-plus'],
        },
      },
      coverage: {
        provider: 'v8',
        reporter: ['text', 'lcov', 'json-summary'],
        include: ['src/utils/**', 'src/stores/**', 'src/composables/**', 'src/components/**', 'src/views/**'],
        exclude: [
          'src/**/*.d.ts',
          'src/**/*.test.ts',
          'src/types/**',
          'src/auto-imports.d.ts',
          'src/components.d.ts',
        ],
      },
    },
  })
)
