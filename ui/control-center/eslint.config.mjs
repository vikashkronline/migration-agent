import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import angular from 'angular-eslint';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
  { ignores: ['node_modules/**', '.angular/**', 'tests/artifacts/**'] },
  {
    files: ['src/**/*.ts'],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommendedTypeChecked,
      ...angular.configs.tsRecommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.json', './tsconfig.spec.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    processor: angular.processInlineTemplates,
    rules: {
      '@angular-eslint/component-selector': [
        'error',
        { type: 'element', prefix: ['cc', 'app'], style: 'kebab-case' },
      ],
      '@angular-eslint/directive-selector': [
        'error',
        { type: 'attribute', prefix: 'cc', style: 'camelCase' },
      ],
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
    },
  },
  {
    files: ['src/**/*.html'],
    extends: [...angular.configs.templateRecommended, ...angular.configs.templateAccessibility],
  },
  prettier,
);
