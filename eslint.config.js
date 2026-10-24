import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      'frontend/vendor/**',
      'frontend/dist/**',
      'frontend/public/**',
      'node_modules/**'
    ]
  },
  ...tseslint.configs.recommended,
  {
    files: ['frontend/src/**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/no-empty-function': 'off'
    }
  }
);
