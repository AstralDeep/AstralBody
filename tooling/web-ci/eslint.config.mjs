import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: [
      "backend/webrender/static/vendor/**",
      "backend/webrender/static/**/*.min.js",
    ],
  },
  {
    ...js.configs.recommended,
    files: ["backend/webrender/static/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
      globals: {
        ...globals.browser,
        // Plotly is loaded by the tracked shell before this classic script.
        Plotly: "readonly",
      },
    },
    linterOptions: {
      reportUnusedDisableDirectives: "error",
    },
    rules: {
      ...js.configs.recommended.rules,
      // Existing storage/focus/render cleanup is deliberately best-effort.
      "no-empty": ["error", { allowEmptyCatch: true }],
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          caughtErrors: "none",
          // `k` is the key-existence sentinel in the background-task map loop.
          varsIgnorePattern: "^(?:_|k$)",
        },
      ],
      // ESLint 10 flags the defensive pre-try array initializer even though
      // the catch returns; changing shipped client behavior is outside T005.
      "no-useless-assignment": "off",
    },
  },
  {
    ...js.configs.recommended,
    files: ["tooling/web-ci/**/*.mjs", "tooling/web-ci/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      // Playwright specs are Node modules whose page callbacks are evaluated
      // in a browser realm, so both sets are intentional in tracked tests.
      globals: {
        ...globals.node,
        ...globals.browser,
      },
    },
    linterOptions: {
      reportUnusedDisableDirectives: "error",
    },
  },
];
