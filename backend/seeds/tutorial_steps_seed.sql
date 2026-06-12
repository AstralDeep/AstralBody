-- Canonical tutorial steps — rewritten by feature 030-wiring-onboarding.
--
-- Idempotent: every INSERT is ON CONFLICT (slug) DO NOTHING, so re-running
-- never duplicates rows or overwrites admin edits (admins rewrite copy in
-- Tutorial admin; slug is the stable identity and is create-only).
--
-- Because DO NOTHING means edited copy under an EXISTING slug never reaches
-- an already-seeded database, this rewrite uses all-new slugs. The pre-030
-- steps (welcome, chat-with-agent, personalize-*, open-agents-panel,
-- enable-agents, open-audit-log, give-feedback, finish, admin-feedback-*,
-- admin-tutorial-editor) are archived once by
-- Database._migrate_tutorial_steps_030: four of them targeted UI removed by
-- feature 026 (the React feedback control and the sdui ParamPicker panels)
-- and the rest described the pre-030 enablement flow and a Quarantine admin
-- tab that no longer exists. Archived rows stay restorable from Tutorial
-- admin.
--
-- Copy rules: plain text only (the tour card renders via textContent),
-- title <= 120 chars, body <= 1000 chars. target_key must match a real
-- [data-tour-target] anchor: chat.input + canvas.workspace (shell.html),
-- topbar.settings / topbar.brand (chrome/topbar.py), or sidebar.<menu-key>
-- for settings-menu entries (auto-opens the menu while highlighted).

-- User flow (audience='user') -----------------------------------------------
INSERT INTO tutorial_step (slug, audience, display_order, target_kind, target_key, title, body)
VALUES
    ('welcome-tour', 'user', 10, 'none', NULL,
     'Welcome to AstralDeep',
     'AstralDeep is a chat-first workspace: ask in plain language and agents answer with live, interactive results. This one-minute tour points out the main controls. Use Next and Back to move through it, or Skip tour at any time — you can replay it later from Settings, under Take the tour.'),

    ('meet-the-canvas', 'user', 20, 'static', 'canvas.workspace',
     'The canvas — where results appear',
     'The highlighted area is your canvas. When agents respond with rich components — dashboards, charts, tables, timelines, cited briefs — they land here and stay with the chat, so later answers can build on earlier ones. On a fresh account it starts with example requests you can run with one click.'),

    ('turn-on-agents', 'user', 30, 'static', 'canvas.workspace',
     'Turn your agents on',
     'New accounts start with every agent switched off, so replies are plain text until you say otherwise. The fastest fix is the welcome card on the canvas: Enable recommended agents switches on read-only access for the built-in agents in one click — search, data, file and system reads, never write. While your agents are all off, the same buttons appear under replies answered without them — and you can enable or fine-tune agents any time from Agents & permissions in Settings.'),

    ('ask-in-plain-language', 'user', 40, 'static', 'chat.input',
     'Ask in plain language',
     'This is the chat panel — type what you need and press Send. Try a live weather dashboard, a cited research brief on a topic you care about, or a summary of a web page. Agents pick the right tools, stream their progress, and render results to the canvas. Follow-up messages refine what''s already there, and every chat keeps its own canvas and history.'),

    ('open-settings-menu', 'user', 50, 'static', 'topbar.settings',
     'Settings — everything else lives here',
     'The Settings button in the top bar opens the menu for your account: Agents & permissions, LLM settings, Personalization, Audit log, Theme, and the Workspace timeline — plus the User guide, this tour, and sign out. The next few steps walk through the ones worth knowing on day one.'),

    ('agents-and-permissions', 'user', 60, 'static', 'sidebar.agents',
     'Agents & permissions',
     'This is the fine-grained companion to the one-click enable: browse every agent available to you (the built-ins live under the Public tab), open one to see its tools, then switch whole permission sections on or off — or override a single tool — and press Save permissions. Nothing an agent does ever exceeds what you''ve granted here, and you can change your mind at any time.'),

    ('personalize-your-assistant', 'user', 70, 'static', 'sidebar.personalization',
     'Make it yours',
     'Personalization is where the assistant learns to work your way: set your profession and goals, review the durable memory it keeps across sessions, enable skills, and manage scheduled jobs and dreaming — the background pass that promotes recurring signals into long-term memory. Personality shapes tone only; it never weakens privacy or safety rules.'),

    ('review-your-audit-log', 'user', 80, 'static', 'sidebar.audit',
     'Your private audit log',
     'Every sign-in, agent action, and tool call on your account is recorded in an append-only, signed log that only you can see. Open it any time to verify exactly what happened — filter by event class or outcome, and drill into any entry for the full details.'),

    ('workspace-timeline', 'user', 90, 'static', 'sidebar.timeline',
     'Step back through your workspace',
     'The Workspace timeline shows a read-only snapshot of your canvas after each turn of the conversation, so you can see how a result took shape. Browsing the past never changes the present — your live workspace stays exactly as you left it.'),

    ('help-anytime', 'user', 100, 'static', 'sidebar.guide',
     'Help, whenever you need it',
     'The User guide covers every surface in more depth — attachments, voice, themes, privacy, and what data stays yours. And if you ever want this walkthrough again, Take the tour sits right above it in this menu.'),

    ('tour-complete', 'user', 110, 'none', NULL,
     'You''re all set',
     'That''s the tour. Enable your agents if you haven''t yet, then ask your first question — or run one of the examples waiting on the canvas. Happy building.')

ON CONFLICT (slug) DO NOTHING;

-- Admin flow (audience='admin', appended after the user flow) ----------------
INSERT INTO tutorial_step (slug, audience, display_order, target_kind, target_key, title, body)
VALUES
    ('admin-tool-quality', 'admin', 200, 'static', 'sidebar.tool-quality',
     'Admin: Tool quality',
     'Tool quality lists underperforming tools across all agents, flagged by failure rate and negative feedback over a rolling window — so you can spot trouble before users report it. Each entry shows the dispatch counts and categories behind the flag.'),

    ('admin-knowledge-proposals', 'admin', 210, 'static', 'sidebar.tool-quality',
     'Admin: Knowledge proposals',
     'When the system finds a likely fix for a flagged tool, it drafts a knowledge-update proposal with the evidence and the exact diff. Review it on the same Tool quality surface and Approve & apply or Reject — nothing changes without an admin decision.'),

    ('admin-edit-this-tour', 'admin', 220, 'static', 'sidebar.tutorial-admin',
     'Admin: Edit this tour',
     'Tutorial admin lets you reshape this tour: edit any step''s title, copy, audience, order, or highlight target; add new steps; or archive ones you no longer want (and restore them later). Changes go live the next time anyone starts the tour, and every edit is kept in the step''s revision history.')

ON CONFLICT (slug) DO NOTHING;
