/**
 * Temporary display-only runtime values for the mock dashboard.
 *
 * The deployed backend remains the source of truth for Bedrock configuration. This
 * fallback keeps the standalone dashboard useful until its read-only API is wired.
 */
const FALLBACK_RUNTIME_CONFIG = {
  region: "us-east-1",
  modelId: "us.amazon.nova-2-lite-v1:0",
} as const;

export const RUNTIME_CONFIG = {
  region: import.meta.env.VITE_ARCUS_AWS_REGION || FALLBACK_RUNTIME_CONFIG.region,
  modelId:
    import.meta.env.VITE_ARCUS_BEDROCK_MODEL_ID || FALLBACK_RUNTIME_CONFIG.modelId,
} as const;
