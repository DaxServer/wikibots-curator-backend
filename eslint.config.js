import js from '@eslint/js'
import tsParser from '@typescript-eslint/parser'
import vueParser from 'vue-eslint-parser'
import vuePlugin from 'eslint-plugin-vue'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import prettierConfig from 'eslint-config-prettier'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

// Get the directory name of the current module
const __dirname = fileURLToPath(new URL('.', import.meta.url))

// Helper to create a relative path from the project root
const resolvePath = (relativePath) => path.resolve(__dirname, relativePath)

/** @type {import('eslint').Linter.FlatConfig[]} */
export default [
  // Base JS config
  js.configs.recommended,

  // Global ignores
  {
    ignores: ['**/node_modules/**', '**/dist/**', '**/.git/**', '**/*.js', '**/*.mjs', '**/*.cjs'],
  },

  // Backend TypeScript files
  {
    files: ['backend/src/**/*.ts'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: resolvePath('backend/tsconfig.json'),
        tsconfigRootDir: __dirname,
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
    },
    rules: {
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-undef': 'off',
      '@typescript-eslint/explicit-function-return-type': [
        'error',
        {
          allowExpressions: true,
          allowTypedFunctionExpressions: true,
        },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
    },
  },

  // Frontend TypeScript files
  {
    files: ['frontend/**/*.ts'],
    ignores: ['**/dist/**', '**/node_modules/**', '**/*.d.ts', '**/env.d.ts', '**/components.d.ts'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: './tsconfig.app.json',
        tsconfigRootDir: resolvePath('frontend'),
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
    },
    rules: {
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-undef': 'off',
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
    },
  },

  // Type declaration files
  {
    files: ['**/*.d.ts'],
    rules: {
      'eslint-disable': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      'no-var': 'off',
      'no-unused-vars': 'off',
    },
  },

  // Vite config files
  {
    files: ['**/vite.config.*'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: null, // Disable project-based type checking for this file
        sourceType: 'module',
        ecmaVersion: 'latest',
      },
    },
    rules: {
      'no-console': 'off',
      'import/no-default-export': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unsafe-return': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
    },
  },

  // Vue files
  {
    files: ['frontend/src/**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: {
          ts: tsParser,
          js: 'espree',
        },
        project: './tsconfig.app.json',
        tsconfigRootDir: resolvePath('frontend'),
        ecmaVersion: 'latest',
        sourceType: 'module',
        extraFileExtensions: ['.vue'],
      },
    },
    plugins: {
      vue: vuePlugin,
    },
    rules: {
      'vue/multi-word-component-names': 'off',
      'vue/block-order': [
        'error',
        {
          order: ['script', 'template', 'style'],
        },
      ],
    },
  },

  // Prettier config (must be last)
  {
    files: ['**/*.ts', '**/*.vue'],
    ...prettierConfig,
  },
]
