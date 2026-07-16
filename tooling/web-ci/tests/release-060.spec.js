import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";

import { expect, test } from "@playwright/test";


const PROMPT = "Roll exactly six six-sided dice and show the normalized results.";
const REQUIRED_LIFECYCLE_STATES = new Set(["starting", "online", "updating", "failed", "offline"]);


function requiredEnvironment(name) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required for the qualifying browser lane`);
  return value;
}


function canonicalSha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}


async function atomicJson(path, value) {
  const bytes = Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8");
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(temporary, bytes, { flag: "wx", mode: 0o600 });
  await rename(temporary, path);
  return canonicalSha256(bytes);
}


function normalizeBaseUrl(raw) {
  const parsed = new URL(raw);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password
      || parsed.search || parsed.hash
      || ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname.toLowerCase())) {
    throw new Error("ASTRAL_RELEASE_BASE_URL must be non-loopback HTTPS without credentials or request data");
  }
  return raw.replace(/\/+$/u, "");
}


function stagingEnvironment(stage, baseUrl) {
  const required = [
    "authentication_posture",
    "candidate_image_reference",
    "candidate_image_sha256",
    "database_posture",
    "deployed_at",
    "deployment_run_id",
    "endpoint",
    "environment_id",
    "fixture_manifest_sha256",
    "keycloak_realm_sha256",
    "macos_personal_agent_host",
    "migrated_schema_revision",
    "representative_dataset_sha256",
    "source_schema_revision",
    "topology",
    "worker_paths",
  ];
  for (const field of required) {
    if (stage[field] === undefined || stage[field] === null) {
      throw new Error(`trusted staging output is missing ${field}`);
    }
  }
  if (stage.endpoint.replace(/\/+$/u, "") !== baseUrl) {
    throw new Error("browser base URL differs from the staged endpoint");
  }
  return Object.fromEntries(required.map((field) => [field, stage[field]]));
}


function runnerIdentity(imageRef) {
  const os = requiredEnvironment("RUNNER_OS").toLowerCase();
  const rawArchitecture = requiredEnvironment("RUNNER_ARCH").toLowerCase();
  const architecture = { x64: "x86_64", x86_64: "x86_64", arm64: "arm64" }[rawArchitecture];
  const runnerEnvironment = requiredEnvironment("ASTRAL_RUNNER_ENVIRONMENT");
  if (os !== "linux" || !architecture
      || !["github_hosted", "self_hosted"].includes(runnerEnvironment)) {
    throw new Error("browser runner identity is outside the release schema");
  }
  return {
    os,
    architecture,
    runner_image: imageRef,
    runner_name: requiredEnvironment("RUNNER_NAME"),
    runner_environment: runnerEnvironment,
  };
}


function workflowIdentity() {
  const attempt = Number.parseInt(requiredEnvironment("GITHUB_RUN_ATTEMPT"), 10);
  if (!Number.isSafeInteger(attempt) || attempt < 1) throw new Error("GITHUB_RUN_ATTEMPT is invalid");
  return {
    name: requiredEnvironment("GITHUB_WORKFLOW"),
    run_id: requiredEnvironment("GITHUB_RUN_ID"),
    run_attempt: attempt,
    job_id: requiredEnvironment("GITHUB_JOB"),
  };
}


function passedCheck(id, durationMs, evidenceArtifact, measurements = []) {
  return {
    id,
    outcome: "passed",
    duration_ms: Math.max(0, Math.round(durationMs)),
    detail_code: null,
    applicability_reason: null,
    measurements,
    evidence_artifacts: [evidenceArtifact],
  };
}


async function installWireObserver(page) {
  const observed = {
    agentLifecycle: [],
    chatStatuses: [],
    operationStatuses: [],
    registerTokens: [],
    snapshots: [],
    socketCloses: 0,
    socketOpens: 0,
  };
  page.on("websocket", (socket) => {
    observed.socketOpens += 1;
    socket.on("framesent", ({ payload }) => {
      try {
        const frame = JSON.parse(payload);
        if (frame.type === "register_ui") observed.registerTokens.push(frame.token);
      } catch {
        // Non-JSON frames cannot be authentication registrations.
      }
    });
    socket.on("close", () => { observed.socketCloses += 1; });
    socket.on("framereceived", ({ payload }) => {
      let frame;
      try {
        frame = JSON.parse(payload);
      } catch {
        return;
      }
      if (frame.type === "operation_status") {
        observed.operationStatuses.push({
          action: frame.action,
          operationId: frame.operation_id,
          sequence: frame.sequence,
          state: frame.state,
          terminal: frame.terminal,
        });
      } else if (frame.type === "agent_lifecycle") {
        observed.agentLifecycle.push({
          agentId: frame.agent_id,
          generation: frame.lifecycle_generation,
          revision: frame.state_revision,
          state: frame.state,
        });
      } else if (frame.type === "conversation_snapshot") {
        observed.snapshots.push({
          chatId: frame.chat_id,
          purpose: frame.snapshot_purpose,
          renderRevision: frame.render_revision,
          snapshotId: frame.snapshot_id,
        });
      } else if (frame.type === "chat_status") {
        observed.chatStatuses.push(frame.status);
      }
    });
  });
  await page.addInitScript(() => {
    Object.defineProperty(window, "__astralReleaseWelcomeAfterLocatedChat", {
      value: false,
      writable: true,
    });
    const startWelcomeGuard = () => {
      const canvas = document.querySelector("#astral-canvas");
      if (!canvas) return;
      new MutationObserver(() => {
        const located = Object.keys(localStorage).some((key) => key.startsWith("astraldeep.active_chat.v1."));
        if (located && canvas.querySelector('[data-component-id^="wel_"]')) {
          window.__astralReleaseWelcomeAfterLocatedChat = true;
        }
      }).observe(canvas, { childList: true, subtree: true });
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", startWelcomeGuard, { once: true });
    } else {
      startWelcomeGuard();
    }
  });
  return observed;
}


async function seedPriorPrincipalDecoy(page, baseUrl) {
  const staleToken = `x.${Buffer.from(JSON.stringify({
    iss: "https://stale.invalid/realms/Astral",
    sub: "prior-principal",
  })).toString("base64url")}.x`;
  const origin = new URL(baseUrl).origin;
  await page.addInitScript(({ expectedOrigin, value }) => {
    if (location.origin === expectedOrigin) {
      sessionStorage.setItem("astraldeep.token", value);
    }
  }, { expectedOrigin: origin, value: staleToken });
  return staleToken;
}


function jwtSubject(token) {
  const payload = token.split(".")[1];
  if (!payload) return null;
  return JSON.parse(Buffer.from(payload, "base64url").toString("utf8")).sub ?? null;
}


async function verifyCurrentSessionOwnsWebSocket(page, wire, staleToken) {
  const session = await page.evaluate(async () => {
    const response = await fetch("/auth/session", { credentials: "same-origin" });
    return response.json();
  });
  expect(session.authenticated).toBe(true);
  await expect.poll(() => wire.registerTokens.length, { timeout: 30_000 }).toBeGreaterThan(0);
  expect(wire.registerTokens[0]).toBe(session.access_token);
  expect(wire.registerTokens[0]).not.toBe(staleToken);
  expect(jwtSubject(wire.registerTokens[0])).toBe(session.user_id);
}


async function signInThroughKeycloak(page, baseUrl, username, password) {
  const started = performance.now();
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  const usernameField = page.locator('input[name="username"]');
  await usernameField.waitFor({ state: "visible", timeout: 30_000 });
  expect(new URL(page.url()).origin).not.toBe(new URL(baseUrl).origin);
  await usernameField.fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('button[type="submit"], input[type="submit"]').first().click();
  await page.waitForURL((url) => url.origin === new URL(baseUrl).origin, { timeout: 60_000 });
  await expect(page.locator("#astral-input")).toBeVisible({ timeout: 30_000 });
  const leakedStorage = await page.evaluate(() => [...Object.keys(localStorage), ...Object.keys(sessionStorage)]
    .filter((key) => /(?:access|refresh)[_-]?token|password|secret/iu.test(key)));
  expect(leakedStorage).toEqual([]);
  return performance.now() - started;
}


async function runRenderedChat(page) {
  const started = performance.now();
  await page.getByRole("button", { name: "New chat" }).click();
  const input = page.locator("#astral-input");
  await input.fill(PROMPT);
  await input.press("Enter");
  await expect(page.locator("#astral-chat")).toContainText(PROMPT, { timeout: 10_000 });
  const assistant = page.locator("#astral-chat > .justify-start").last();
  await expect(assistant).toBeVisible({ timeout: 240_000 });
  await expect(assistant).toContainText(/(?:six-sided|d6)/iu, { timeout: 240_000 });
  await expect(page.locator("#astral-status")).toHaveAttribute("aria-busy", "false", { timeout: 240_000 });
  await expect(page.locator("#astral-canvas-skeleton")).toHaveCount(0, { timeout: 30_000 });
  const transcript = (await page.locator("#astral-chat").innerText()).trim();
  const canvas = (await page.locator("#astral-canvas").innerText()).trim();
  expect(transcript).toMatch(/\b6\b/u);
  expect(transcript.toLowerCase()).toMatch(/(?:six-sided|d6)/u);
  return { canvas, durationMs: performance.now() - started, transcript };
}


async function runResumeTrials(page, expectedTranscript, expectedCanvas) {
  const latencies = [];
  for (let trial = 0; trial < 20; trial += 1) {
    const started = performance.now();
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect.poll(async () => (await page.locator("#astral-chat").innerText()).trim(), {
      timeout: 5_000,
    }).toBe(expectedTranscript);
    await expect.poll(async () => (await page.locator("#astral-canvas").innerText()).trim(), {
      timeout: 5_000,
    }).toBe(expectedCanvas);
    latencies.push(performance.now() - started);
  }
  expect(await page.evaluate(() => window.__astralReleaseWelcomeAfterLocatedChat)).toBe(false);
  return latencies;
}


async function openSettingsSurface(page, label) {
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("menuitem", { name: label, exact: true }).click();
  await expect(page.locator("#astral-modal .astral-modal-card")).toBeVisible({ timeout: 15_000 });
}


async function runPersonalAgentAuthoring(page, wire) {
  const started = performance.now();
  await openSettingsSurface(page, "My agents");
  const name = `Release 060 ${randomUUID().slice(0, 8)}`;
  await page.locator('#astral-modal input[name="agent_name"]').fill(name);
  await page.locator('#astral-modal textarea[name="description"]').fill(
    "Greet only its owner using a deterministic local tool and no network access.",
  );
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.locator('#astral-modal textarea[name="specification"]')).toBeVisible({ timeout: 30_000 });
  await page.locator('#astral-modal textarea[name="specification"]').fill(
    "Greet the owner on request. Use one local greet tool and return a short plain-text greeting.",
  );
  await page.getByRole("button", { name: "Save & continue", exact: true }).click();
  await expect(page.locator("#astral-modal")).toContainText("Clarify", { timeout: 60_000 });
  const answers = page.locator('#astral-modal textarea[name^="q"]');
  for (let index = 0; index < await answers.count(); index += 1) {
    await answers.nth(index).fill("Use deterministic owner-only behavior with no external egress.");
  }
  await page.getByRole("button", { name: "Save & continue", exact: true }).click();
  await expect(page.locator('#astral-modal textarea[name="tools"]')).toBeVisible({ timeout: 60_000 });
  await page.locator('#astral-modal textarea[name="tools"]').fill("greet | tools:read | greet the owner");
  await page.locator('#astral-modal input[name="scopes"]').fill("tools:read");
  await page.getByRole("button", { name: "Save & continue", exact: true }).click();
  await expect(page.locator('#astral-modal textarea[name="tasks"]')).toBeVisible({ timeout: 60_000 });
  await page.locator('#astral-modal textarea[name="tasks"]').fill("Validate the request\nCall greet once\nReturn the greeting");
  await page.getByRole("button", { name: "Save & continue", exact: true }).click();
  await page.getByRole("button", { name: "Run Analyze", exact: true }).click();
  await expect(page.locator("#astral-modal")).toContainText("Analyze passed", { timeout: 60_000 });
  const statuses = wire.operationStatuses.filter((item) => item.action?.startsWith("chrome_author_"));
  expect(statuses.some((item) => item.terminal === true && item.state === "completed")).toBe(true);
  expect(statuses.some((item) => item.terminal === true && item.state === "failed")).toBe(false);
  return { durationMs: performance.now() - started, name };
}


async function verifyLifecycle(wire, agentId, expectedStates) {
  const started = performance.now();
  await expect.poll(() => {
    const events = wire.agentLifecycle.filter((event) => event.agentId === agentId);
    return [...new Set(events.map((event) => event.state))];
  }, { timeout: 120_000 }).toEqual(expect.arrayContaining(expectedStates));
  const events = wire.agentLifecycle.filter((event) => event.agentId === agentId);
  for (const event of events) {
    expect(Number.isSafeInteger(event.generation) && event.generation >= 0).toBe(true);
    expect(Number.isSafeInteger(event.revision) && event.revision >= 0).toBe(true);
    expect(REQUIRED_LIFECYCLE_STATES.has(event.state)).toBe(true);
  }
  return { durationMs: performance.now() - started, events };
}


async function verifyAccessibility(page) {
  const started = performance.now();
  await expect(page.getByRole("status", { name: "Application status" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "New chat" })).toBeEnabled();
  await expect(page.locator("#astral-input")).toHaveAttribute("placeholder", /\S/u);
  const inaccessible = await page.locator("button, input:not([type=hidden]), textarea, select, a[href]").evaluateAll(
    (elements) => elements.filter((element) => {
      const style = getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden") return false;
      const id = element.getAttribute("id");
      const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
      return !(
        element.getAttribute("aria-label")
        || element.getAttribute("title")
        || element.getAttribute("placeholder")
        || element.textContent?.trim()
        || label?.textContent?.trim()
      );
    }).map((element) => element.outerHTML.slice(0, 200)),
  );
  expect(inaccessible).toEqual([]);
  await page.locator("body").press("Tab");
  await expect.poll(() => page.evaluate(() => document.activeElement !== document.body)).toBe(true);
  return { durationMs: performance.now() - started, inspectedControls: await page.locator("button, input, textarea, select, a[href]").count() };
}


test("real Keycloak candidate browser release flow", async ({ context, page }) => {
  test.setTimeout(15 * 60 * 1000);
  const baseUrl = normalizeBaseUrl(requiredEnvironment("ASTRAL_RELEASE_BASE_URL"));
  const candidateSha = requiredEnvironment("ASTRAL_RELEASE_CANDIDATE_SHA");
  const output = resolve(requiredEnvironment("ASTRAL_RELEASE_OUTPUT"));
  const coverageOutput = resolve(requiredEnvironment("ASTRAL_RELEASE_COVERAGE_OUTPUT"));
  const stage = JSON.parse(await readFile(requiredEnvironment("ASTRAL_RELEASE_STAGING_FILE"), "utf8"));
  const staging = stagingEnvironment(stage, baseUrl);
  const imageRef = requiredEnvironment("ASTRAL_PLAYWRIGHT_IMAGE");
  const lifecycleAgent = requiredEnvironment("ASTRAL_RELEASE_LIFECYCLE_AGENT_ID");
  const lifecycleStates = requiredEnvironment("ASTRAL_RELEASE_LIFECYCLE_STATES").split(",").filter(Boolean);
  if (!lifecycleStates.length || lifecycleStates.some((state) => !REQUIRED_LIFECYCLE_STATES.has(state))) {
    throw new Error("ASTRAL_RELEASE_LIFECYCLE_STATES is invalid");
  }
  expect(await context.cookies()).toEqual([]);
  const wire = await installWireObserver(page);
  const stalePriorPrincipalToken = await seedPriorPrincipalDecoy(page, baseUrl);
  await page.coverage.startJSCoverage({ reportAnonymousScripts: false, resetOnNavigation: false });
  const startedAt = new Date().toISOString();
  const rawRoot = resolve(dirname(output), "web-raw");
  const rawArtifacts = new Map();
  const writeRaw = async (name, value) => {
    const path = resolve(rawRoot, `${name}.json`);
    const sha256 = await atomicJson(path, value);
    const artifact = {
      name: `web_${name}`,
      kind: "json_metrics",
      immutable_reference: `bundle://web-raw/${basename(path)}`,
      sha256,
    };
    rawArtifacts.set(name, artifact);
    return artifact;
  };

  const signInDuration = await signInThroughKeycloak(
    page,
    baseUrl,
    requiredEnvironment("ASTRAL_RELEASE_USERNAME"),
    requiredEnvironment("ASTRAL_RELEASE_PASSWORD"),
  );
  await verifyCurrentSessionOwnsWebSocket(page, wire, stalePriorPrincipalToken);
  const signInArtifact = await writeRaw("sign_in", {
    authenticatedOrigin: new URL(page.url()).origin,
    durationMs: Math.round(signInDuration),
    freshContext: true,
    method: "keycloak_ui_authorization_code_pkce",
    sharedTabStaleTokenRejected: true,
    websocketPrincipalMatchesCookieSession: true,
  });

  const chat = await runRenderedChat(page);
  const chatArtifact = await writeRaw("rendered_chat", {
    durationMs: Math.round(chat.durationMs),
    normalizedDiceContractObserved: true,
    promptSha256: canonicalSha256(Buffer.from(PROMPT, "utf8")),
  });

  const resumeStarted = performance.now();
  const resumeLatencies = await runResumeTrials(page, chat.transcript, chat.canvas);
  const resumeDuration = performance.now() - resumeStarted;
  const resumeArtifact = await writeRaw("reconnect_resume", {
    latenciesMs: resumeLatencies.map(Math.round),
    maxLatencyMs: Math.round(Math.max(...resumeLatencies)),
    successfulTrials: resumeLatencies.length,
    trialCount: 20,
  });

  const authoring = await runPersonalAgentAuthoring(page, wire);
  const authoringArtifact = await writeRaw("personal_agent", {
    analyzePassed: true,
    durationMs: Math.round(authoring.durationMs),
    generatedTestIdentitySha256: canonicalSha256(Buffer.from(authoring.name, "utf8")),
  });

  const lifecycle = await verifyLifecycle(wire, lifecycleAgent, lifecycleStates);
  const lifecycleArtifact = await writeRaw("agent_lifecycle", {
    agentIdSha256: canonicalSha256(Buffer.from(lifecycleAgent, "utf8")),
    durationMs: Math.round(lifecycle.durationMs),
    events: lifecycle.events.map(({ generation, revision, state }) => ({ generation, revision, state })),
    requiredStates: lifecycleStates,
  });

  const accessibility = await verifyAccessibility(page);
  const accessibilityArtifact = await writeRaw("accessibility_semantics", accessibility);
  const coverage = await page.coverage.stopJSCoverage();
  await atomicJson(coverageOutput, coverage);
  const completedAt = new Date().toISOString();
  const report = {
    document_type: "platform_evidence",
    schema_version: 1,
    evidence_id: randomUUID(),
    candidate_sha: candidateSha,
    release_id: requiredEnvironment("ASTRAL_RELEASE_ID"),
    release_version: requiredEnvironment("ASTRAL_RELEASE_VERSION"),
    platform: "web",
    target_description: "Backend-served web client in the pinned official Playwright Chromium image",
    artifact: {
      name: "astraldeep-web-deployment",
      kind: "web_deployment",
      immutable_reference: `oci://${staging.candidate_image_reference}`,
      sha256: staging.candidate_image_sha256,
      build_identity: `candidate-container:${candidateSha}`,
    },
    staging_environment: staging,
    runner: runnerIdentity(imageRef),
    workflow: workflowIdentity(),
    started_at: startedAt,
    completed_at: completedAt,
    outcome: "passed",
    unavailable_reason: null,
    unavailability_observation: null,
    checks: [
      passedCheck("sign_in", signInDuration, signInArtifact),
      passedCheck("rendered_chat", chat.durationMs, chatArtifact),
      passedCheck("reconnect_resume", resumeDuration, resumeArtifact, [
        {
          metric: "trial_count",
          aggregation: "total",
          value: 20,
          unit: "count",
          sample_count: 20,
          comparator: "gte",
          threshold: 20,
        },
        {
          metric: "resume_success_rate",
          aggregation: "rate",
          value: 100,
          unit: "percent",
          sample_count: 20,
          comparator: "gte",
          threshold: 100,
        },
      ]),
      passedCheck("agent_lifecycle", lifecycle.durationMs, lifecycleArtifact),
      passedCheck("personal_agent", authoring.durationMs, authoringArtifact),
      passedCheck("accessibility_semantics", accessibility.durationMs, accessibilityArtifact),
    ],
  };
  await atomicJson(output, report);
  expect(rawArtifacts.size).toBe(6);
});
