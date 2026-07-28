# Arcus infrastructure runbook

This directory contains the AWS SAM template for the bounded Arcus PR-review pipeline. Run commands from the repository root.

## Resources and cost controls

The stack provisions:

- A private, encrypted, versioned S3 artifact bucket. PR artifacts expire after `ArtifactRetentionDays`; noncurrent PR and graph versions expire after `NoncurrentVersionRetentionDays`.
- An encrypted, on-demand DynamoDB table with TTL and maximum on-demand read/write units.
- A public API Gateway HTTP API exposing only `POST /webhook`, with a low route throttle.
- The webhook, Fetch PR, Ensure Repository Graph, Context Builder, Consistency Checker, Bug Hunter, Fix Suggester, and Reporter Lambdas with timeout limits. Admission quotas and the account-level Lambda quota bound hackathon concurrency without per-function reservations.
- A Standard Step Functions workflow with a twelve-minute execution timeout, per-task timeouts, and one retry only for Lambda infrastructure errors.
- Secrets Manager containers for the webhook HMAC secret and GitHub App private key.
- An SNS topic and CloudWatch alarms for webhook volume/throttling, pipeline starts/failures, Bedrock calls/output tokens, and DynamoDB throttling.

AWS resources may incur charges. S3, DynamoDB, and both secrets use `DeletionPolicy: RetainExceptOnCreate`: a failed initial stack creation cleans them up, while deleting a successfully created stack retains them. CloudWatch alarms notify but do not stop spend automatically.

## Prerequisites

Install and configure:

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- AWS CLI
- AWS SAM CLI with `python-uv` beta-feature support
- AWS credentials authorized to create the stack, including named IAM roles
- A GitHub App with repository contents read, pull-request read, and issue-comment read/write access
- Bedrock model access in `us-east-1`

Confirm the target account and region before deployment:

```powershell
aws sts get-caller-identity
aws configure get region
```

For a named profile, set `$env:AWS_PROFILE = "your-profile"` for the session or add `profile = "your-profile"` to the appropriate global section of your local `infra/samconfig.toml`.

## Configure deployment parameters

Create the local SAM configuration:

```powershell
Copy-Item infra/samconfig.toml.example infra/samconfig.toml
```

`infra/samconfig.toml` is ignored by Git. Replace every placeholder before deploying:

- `BedrockModelId` and `BedrockFoundationModelId`: the matching inference-profile and foundation-model IDs.
- `GitHubAppId`: the positive numeric App ID. The checked-in examples use a nonzero placeholder that must be replaced.
- `AllowedRepositories`: use `*` for every repository accessible to an approved installation, or comma-separated `owner/repo` names for an explicit allowlist.
- `AllowedInstallationIds`: use `*` only while the GitHub App is private and installable solely on the owning account; otherwise use comma-separated positive installation IDs.
- `ReviewsPerRepositoryDay` and `ReviewsPerInstallationHour`: hard admission quotas.

`AllowedRepositories=*` plus `AllowedInstallationIds=*` trusts every installation of the configured App. Before changing the App to public, replace the installation wildcard with approved IDs and redeploy. Per-installation quotas do not provide an aggregate cost ceiling when an unbounded number of public installations can be created.
- `AlarmNotificationEmail`: optional alarm recipient. Confirm the SNS subscription email after deployment.

The template also exposes limits for webhook bytes, secret-cache TTL, AI operations, output tokens, prompt bytes, findings, changed files, diff bytes, repository archive bytes, extracted repository bytes, archive entries, graph bytes, envelope bytes, API throttle, artifact retention, and DynamoDB request units. Keep the defaults unless the demo needs a measured adjustment. Never place secret values, private keys, or credentials in SAM configuration.

Synchronize the locked environment:

```powershell
uv sync --locked --dev
```

## Validate

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src/arcus/contracts src/arcus/graph src/arcus/github
uv run pytest tests/unit
uv run pytest -m contract
uv run pytest tests/integration
uv build
sam validate --template-file infra/template.yaml --lint
```

## Pre-deployment checklist

The automated checks use mocks and do not call live AWS, Bedrock, or GitHub services. Before approving the first deployment change set:

- Replace the example `GitHubAppId=123456` in your local `infra/samconfig.toml` with the real positive GitHub App ID.
- Replace the repository and installation placeholders with the narrowest practical `AllowedRepositories` and `AllowedInstallationIds` allowlists.
- Verify that `BedrockModelId` and `BedrockFoundationModelId` identify the same accessible model in `us-east-1`.
- Review the repository/day and installation/hour quotas, AI limits, API throttle, retention periods, and DynamoDB throughput caps for the demo.
- Set `AlarmNotificationEmail` if alarms must notify an operator; an alarm without a confirmed SNS subscription does not provide an actionable notification.
- Confirm the AWS account, region, and profile again immediately before running `sam deploy`.

Immediately after deployment, but before enabling or redelivering the GitHub webhook:

- Populate both Secrets Manager containers with the webhook HMAC secret and GitHub App private key.
- Confirm the SNS email subscription if one was configured.
- Run the unsigned-request check, then one allowed signed webhook smoke test.
- Inspect the first Step Functions execution, GitHub comment, DynamoDB history row, and CloudWatch alarms/logs.

## Build and deploy

Build before every deployment that changes source or the template:

```powershell
sam build --config-file infra/samconfig.toml
sam deploy --config-file infra/samconfig.toml
```

For the isolated demo stack:

```powershell
sam build --config-file infra/samconfig.toml --config-env demo
sam deploy --config-file infra/samconfig.toml --config-env demo
```

Both profiles use `.aws-sam/build/`; rebuild when switching environments. Deployment asks for change-set confirmation and does not apply changes until approved.

## Populate secrets

Capture stack outputs, then populate the empty secret containers from files outside the repository:

```powershell
$stackName = "arcus-dev"

$webhookSecretArn = aws cloudformation describe-stacks `
  --stack-name $stackName `
  --query "Stacks[0].Outputs[?OutputKey=='WebhookSecretArn'].OutputValue | [0]" `
  --output text

$privateKeySecretArn = aws cloudformation describe-stacks `
  --stack-name $stackName `
  --query "Stacks[0].Outputs[?OutputKey=='GitHubAppPrivateKeySecretArn'].OutputValue | [0]" `
  --output text

aws secretsmanager put-secret-value `
  --secret-id $webhookSecretArn `
  --secret-string file://C:/secure/arcus-webhook-secret.txt

aws secretsmanager put-secret-value `
  --secret-id $privateKeySecretArn `
  --secret-string file://C:/secure/github-app-private-key.pem
```

The webhook file must exactly match the GitHub App webhook secret. Avoid an accidental trailing newline. Never commit or print either secret.

## Configure the GitHub App

In the GitHub App settings:

- Set the payload URL to the `WebhookUrl` stack output.
- Select `application/json`.
- Set the same HMAC secret stored in `WebhookSecretArn`.
- Subscribe to pull-request events.
- Install the App on only the repositories included in `AllowedRepositories`.

The handler starts reviews for `opened` and `synchronize`. Valid but irrelevant, disallowed, duplicate, or quota-exhausted deliveries receive `202` so GitHub does not amplify cost through redelivery. Invalid signatures are rejected.

## Configure dashboard login (GitHub OAuth)

The dashboard requires each visitor to log in with their own GitHub account before it shows any repository or review data. This is a **separate** GitHub OAuth App from the GitHub App used by the review pipeline; the OAuth App only ever acts as the logged-in human, never as an installation.

1. In GitHub, create a new OAuth App (Settings → Developer settings → OAuth Apps → New OAuth App):
   - **Homepage URL**: your deployed dashboard origin (e.g. the Amplify URL).
   - **Authorization callback URL**: `https://{api-id}.execute-api.{region}.amazonaws.com/auth/callback`, matching the deployed `DashboardHttpApi`. You will only know the exact API ID after the first deploy; deploy once with a placeholder, read `OAuthLoginUrl`/`DashboardApiUrl` from the stack outputs, then update the OAuth App's callback URL and redeploy with the real value.
   - Copy the generated **Client ID** (public) and **Client Secret** (treat as a secret).
2. Set the following parameters in `infra/samconfig.toml` before deploying:
   - `GitHubOAuthClientId`: the OAuth App's public client ID.
   - `DashboardBaseUrl`: the deployed dashboard origin (no trailing slash). This is also the only allowed CORS origin for the cookie-based `/auth/*` and `/me*` routes.
   - `OAuthRedirectUri`: must exactly match the callback URL registered on the OAuth App.
3. After deployment, populate the two new secrets the same way as the webhook secret and private key:

   ```powershell
   $stackName = "arcus-dev"

   $oauthSecretArn = aws cloudformation describe-stacks `
     --stack-name $stackName `
     --query "Stacks[0].Outputs[?OutputKey=='GitHubOAuthClientSecretArn'].OutputValue | [0]" `
     --output text

   aws secretsmanager put-secret-value `
     --secret-id $oauthSecretArn `
     --secret-string file://C:/secure/arcus-oauth-client-secret.txt
   ```

   `SessionSecret` is auto-generated by CloudFormation; nothing to populate there. Rotating it (via `aws secretsmanager put-secret-value` or `rotate-secret`) immediately invalidates every open dashboard session.
4. In the dashboard's build environment (e.g. AWS Amplify Hosting), set `VITE_API_BASE_URL` to the `DashboardApiUrl` stack output. No client-side login secret is needed; the session is a server-set HttpOnly cookie.

Each user's GitHub access token and repository selection are stored per-account in DynamoDB (`USER#{github_user_id}`), never in the browser. Logging out clears the dashboard's session cookie only; it does not revoke the OAuth grant on GitHub's side (the user can do that from their own GitHub settings).

## Automatic repository context and replay a webhook

Repository graph creation is automatic. On the first accepted PR for a base commit, Ensure Repository Graph downloads a bounded GitHub archive using the installation token, safely extracts Python source into Lambda temporary storage, and writes an immutable graph under `graphs/{owner}/{repo}/commits/{base_sha}.json`. Later PRs with the same base commit reuse that object. If bootstrap fails or a repository exceeds a configured limit, the analysis stages are skipped and Reporter publishes the structured failure.

`scripts/seed_graph.py` remains available only as an operator recovery tool. Normal repository onboarding must not require a local clone or manual graph upload.

For the scripted demo rehearsal, load the same webhook secret stored in Secrets Manager and replay the shared signed payload against the deployed endpoint:

```powershell
$env:ARCUS_WEBHOOK_URL = $webhookUrl
$env:ARCUS_WEBHOOK_SECRET = (Get-Content C:\secure\arcus-webhook-secret.txt -Raw).TrimEnd("`r", "`n")
uv run python scripts/replay_webhook.py
```

The default replay fixture targets `acme/widgets` with installation ID `123456`; either retain those values in a disposable demo stack or provide a saved payload matching the deployed allowlists with `--payload`. The replay script requires HTTP `202` and never calls Bedrock directly; the deployed pipeline performs the review.

## Smoke checks

An unsigned request must return `401`:

```powershell
$webhookUrl = aws cloudformation describe-stacks `
  --stack-name $stackName `
  --query "Stacks[0].Outputs[?OutputKey=='WebhookUrl'].OutputValue | [0]" `
  --output text

curl.exe -i -X POST "$webhookUrl" `
  -H "Content-Type: application/json" `
  --data "{}"
```

After configuring the App and secrets, redeliver an allowed `opened` or `synchronize` event. Expected behavior:

1. GitHub receives HTTP `202`.
2. DynamoDB atomically records delivery/commit claims and both quota counters.
3. Step Functions starts one execution.
4. Fetch PR stores a bounded diff; Ensure Repository Graph creates or reuses the base-commit graph; the agents return valid envelopes.
5. Reporter upserts one marked GitHub comment and one deterministic history row.
6. Replaying the same delivery or repository/PR/commit does not create another logical run.

Inspect executions without starting a long-running process:

```powershell
$stateMachineArn = aws cloudformation describe-stacks `
  --stack-name $stackName `
  --query "Stacks[0].Outputs[?OutputKey=='PipelineStateMachineArn'].OutputValue | [0]" `
  --output text

aws stepfunctions list-executions `
  --state-machine-arn $stateMachineArn `
  --max-results 10

sam logs `
  --name WebhookFunction `
  --stack-name $stackName `
  --region us-east-1 `
  --start-time "10min ago"
```

Logs must not contain secrets, installation tokens, full diffs, prompts, or model responses.

## Emergency AI kill switch

The template deliberately leaves concurrency unreserved because low-quota AWS accounts must keep at least ten executions in the regional unreserved pool. An emergency override can still set each AI Lambda's reserved concurrency to zero. This immediately throttles new invocations and can fail in-flight workflows, so use it only to stop unexpected spend:

```powershell
$functions = @(
  "arcus-dev-agent-consistency-checker",
  "arcus-dev-agent-bug-hunter",
  "arcus-dev-agent-fix-suggester"
)

foreach ($function in $functions) {
  aws lambda put-function-concurrency `
    --function-name $function `
    --reserved-concurrent-executions 0
}
```

Restore normal access by deleting each emergency override; redeployment alone does not manage concurrency when the template omits the property:

```powershell
foreach ($function in $functions) {
  aws lambda delete-function-concurrency `
    --function-name $function
}
```

## Delete a stack

Deletion interrupts processing and is destructive to non-retained resources:

```powershell
sam delete --stack-name arcus-dev --region us-east-1
```

The retained bucket, table, and secrets may continue to incur charges and can cause name collisions on a later deployment. Inspect them explicitly before recreating the stack.

## Troubleshooting

- **`.aws-sam/build/template.yaml` missing:** run `sam build` before deploy.
- **Lambda import error:** rebuild with the `python-uv` beta feature so runtime dependencies come from `uv.lock`.
- **Webhook returns `500`:** verify both secret values, App ID, AWS permissions, and table/state-machine configuration.
- **Webhook returns `401`:** ensure GitHub and Secrets Manager use exactly the same HMAC secret.
- **Webhook returns `202` without an execution:** check repository/installation allowlists, quota counters, action, and duplicate claims.
- **No review comment appears:** inspect Reporter logs and verify GitHub App issue-comment permissions.
- **Graph bootstrap fails:** inspect Ensure Repository Graph logs, GitHub App contents permission, archive limits, and `graphs/{owner}/{repo}/commits/{base_sha}.json` in S3. Analysis is skipped until graph context is available. Use `scripts/seed_graph.py` only for emergency recovery.
- **Bedrock access denied:** verify model access, region, model ID, and the least-privilege model ARNs in `infra/template.yaml`.
- **Resource already exists:** locate the owner stack or retained resource; CloudFormation does not adopt it automatically.
- **S3 bucket name unavailable:** bucket names are global; change the naming strategy instead of creating an unmanaged bucket.
- **Dashboard login redirects to GitHub but never returns:** confirm `OAuthRedirectUri` matches the OAuth App's registered callback URL exactly, including scheme and trailing path.
- **`/auth/callback` returns 400 "invalid or expired OAuth state":** the browser must accept the short-lived `arcus_oauth_state` cookie set by `/auth/login`; check that `DashboardBaseUrl` matches the dashboard's real origin and that the browser is not blocking third-party cookies for the API's domain.
- **`/me` always returns 401 even right after logging in:** the dashboard's `fetch` calls must send `credentials: "include"`, and the API's CORS `AllowOrigins` must be the exact dashboard origin (not `*`) with `AllowCredentials: true`, or the browser drops the session cookie.
- **Logging out does not remove access from GitHub:** by design; `/auth/logout` only clears the local dashboard session. Revoking the OAuth grant itself is done from the user's own GitHub authorized-apps settings.
