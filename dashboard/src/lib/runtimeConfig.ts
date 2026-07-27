/**
 * Display-only runtime values plus the public GitHub App install link.
 *
 * The deployed backend remains the source of truth for Bedrock configuration.
 * `githubAppSlug` is the public slug from the GitHub App's own settings page
 * (never a secret); it only builds a link to GitHub's own installation flow,
 * where the repository owner grants consent. Arcus never installs itself.
 */
const FALLBACK_RUNTIME_CONFIG = {
  region: "us-east-1",
  modelId: "us.amazon.nova-2-lite-v1:0",
} as const;

const githubAppSlug = (import.meta.env.VITE_GITHUB_APP_SLUG ?? "").trim();

export const RUNTIME_CONFIG = {
  region: import.meta.env.VITE_ARCUS_AWS_REGION || FALLBACK_RUNTIME_CONFIG.region,
  modelId:
    import.meta.env.VITE_ARCUS_BEDROCK_MODEL_ID || FALLBACK_RUNTIME_CONFIG.modelId,
  githubAppSlug,
  /** GitHub's own consent screen; null until VITE_GITHUB_APP_SLUG is configured. */
  githubAppInstallUrl: githubAppSlug
    ? `https://github.com/apps/${githubAppSlug}/installations/new`
    : null,
} as const;
