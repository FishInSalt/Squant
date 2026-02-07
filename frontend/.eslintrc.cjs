/* eslint-env node */
module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  parser: 'vue-eslint-parser',
  parserOptions: {
    parser: '@typescript-eslint/parser',
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:vue/vue3-recommended',
  ],
  rules: {
    // Vue
    'vue/multi-word-component-names': 'off',
    'vue/no-v-html': 'off',
    'vue/require-default-prop': 'off',
    'vue/no-setup-props-reactivity-loss': 'warn',
    'vue/max-attributes-per-line': 'off',
    'vue/singleline-html-element-content-newline': 'off',
    'vue/html-self-closing': 'off',
    'vue/html-closing-bracket-newline': 'off',
    'vue/attributes-order': 'off',

    // TypeScript
    '@typescript-eslint/no-explicit-any': 'off',
    '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    '@typescript-eslint/no-empty-function': 'off',

    // General
    'no-console': ['warn', { allow: ['warn', 'error', 'info', 'debug'] }],
    'no-debugger': 'warn',
    'prefer-const': 'warn',
  },
  // unplugin-auto-import 生成的全局变量
  globals: {
    ref: 'readonly',
    computed: 'readonly',
    reactive: 'readonly',
    watch: 'readonly',
    watchEffect: 'readonly',
    onMounted: 'readonly',
    onUnmounted: 'readonly',
    onBeforeUnmount: 'readonly',
    defineProps: 'readonly',
    defineEmits: 'readonly',
    defineExpose: 'readonly',
    withDefaults: 'readonly',
    useRouter: 'readonly',
    useRoute: 'readonly',
    nextTick: 'readonly',
    toRef: 'readonly',
    toRefs: 'readonly',
    unref: 'readonly',
    shallowRef: 'readonly',
  },
  ignorePatterns: [
    'dist/',
    'node_modules/',
    'src/auto-imports.d.ts',
    'src/components.d.ts',
  ],
}
