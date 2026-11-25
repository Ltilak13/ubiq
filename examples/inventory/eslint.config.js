import tseslint from 'typescript-eslint';
export default tseslint.config(
  { ignores: ['node_modules/**', 'reports/**', 'drizzle/**'] },
  ...tseslint.configs.recommended,
);
