-- Seed canonical tutorial steps for feature 005-tooltips-tutorial.
-- Idempotent: re-running this file does not duplicate or overwrite admin edits.
-- Steps are owned by an internal "system" identifier; admin edits will rewrite
-- title/body but preserve slug.

-- User-flow steps (audience='user') ----------------------------------------
INSERT INTO tutorial_step (slug, audience, display_order, target_kind, target_key, title, body)
VALUES
    ('welcome', 'user', 10, 'none', NULL,
     'Welcome to AstralDeep',
     'A quick tour of how intelligent agents help you work. Take a minute now or come back later — your call.'),

    ('chat-with-agent', 'user', 20, 'static', 'chat.input',
     'Chat with an agent',
     'Type a message here to start a conversation. Your agent can search, analyze, and render rich results back to you.'),

    ('open-agents-panel', 'user', 30, 'static', 'sidebar.agents',
     'Browse available agents',
     'Open the Agents panel to see who you can talk to, what tools they have, and how to manage their access.'),

    -- Feature 008-llm-text-only-chat: explicit step nudging users to
    -- turn on at least one agent so they unlock tool-augmented chat.
    -- Until they do, AstralDeep falls back to text-only chat and
    -- shows the persistent banner over the chat surface.
    ('enable-agents', 'user', 35, 'static', 'sidebar.agents',
     'Turn an agent on',
     'Switch on at least one agent to unlock tool-augmented chat. Without it, your agent can talk but can''t act.'),

    ('open-audit-log', 'user', 40, 'static', 'sidebar.audit',
     'Review the audit log',
     'Every agent action is recorded in your private audit log. Check it anytime to verify what happened.'),

    ('give-feedback', 'user', 50, 'static', 'feedback.control',
     'Tell us what worked',
     'Use the feedback control to flag useful or broken results. Your input shapes how the system improves.'),

    ('finish', 'user', 60, 'none', NULL,
     'You''re all set',
     'That''s the tour! Replay it anytime from the sidebar. Happy chatting.')

ON CONFLICT (slug) DO NOTHING;

-- Admin-flow steps (audience='admin', appended after user-flow) ------------
INSERT INTO tutorial_step (slug, audience, display_order, target_kind, target_key, title, body)
VALUES
    ('admin-feedback-flagged', 'admin', 100, 'static', 'sidebar.feedback-admin',
     'Admin: Flagged tools',
     'As an admin, you can see which tools have flagged quality issues. Open Feedback admin to review the data behind a flag.'),

    ('admin-feedback-proposals', 'admin', 110, 'static', 'sidebar.feedback-admin',
     'Admin: Knowledge update proposals',
     'When the system identifies a likely fix for an underperforming tool, it surfaces a proposal here. You decide whether to apply it.'),

    ('admin-feedback-quarantine', 'admin', 120, 'static', 'sidebar.feedback-admin',
     'Admin: Quarantined feedback',
     'Feedback flagged for unsafe content lands in quarantine. Release or dismiss items here to keep the synthesizer pool clean.'),

    ('admin-tutorial-editor', 'admin', 130, 'static', 'sidebar.tutorial-admin',
     'Admin: Edit this tour',
     'You can edit the copy of every step in this tour from the Tutorial admin panel. Changes go live the next time anyone replays.')

ON CONFLICT (slug) DO NOTHING;
