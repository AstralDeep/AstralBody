-- Seed canonical tutorial steps for feature 005-tooltips-tutorial.
-- Idempotent: re-running this file does not duplicate or overwrite admin edits.
-- Steps are owned by an internal "system" identifier; admin edits will rewrite
-- title/body but preserve slug.

-- User-flow steps (audience='user') ----------------------------------------
INSERT INTO tutorial_step (slug, audience, display_order, target_kind, target_key, title, body)
VALUES
    ('welcome', 'user', 10, 'none', NULL,
     'Welcome to AstralBody',
     'Let''s take a quick tour of how AstralBody helps you collaborate with intelligent agents. This will only take a minute — you can skip at any time.'),

    ('chat-with-agent', 'user', 20, 'static', 'chat.input',
     'Chat with an agent',
     'Type a message here to start a conversation. Your message is routed to an agent that can use tools, look things up, and render rich UI back to you.'),

    ('open-agents-panel', 'user', 30, 'static', 'sidebar.agents',
     'Browse available agents',
     'Open the Agents panel to see every agent you can talk to, what tools they have, and how to grant or revoke their access.'),

    -- Feature 008-llm-text-only-chat: explicit step nudging users to
    -- turn on at least one agent so they unlock tool-augmented chat.
    -- Until they do, AstralBody falls back to text-only chat and
    -- shows the persistent banner over the chat surface.
    ('enable-agents', 'user', 35, 'static', 'sidebar.agents',
     'Turn an agent on',
     'Open the Agents panel and switch on at least one agent. Until you do, AstralBody talks to the language model in text-only mode — it can chat, but it can''t take actions on your behalf.'),

    ('open-audit-log', 'user', 40, 'static', 'sidebar.audit',
     'Review the audit log',
     'Every action an agent takes on your behalf is recorded in your private audit log. You can review and verify what happened at any time.'),

    ('give-feedback', 'user', 50, 'static', 'feedback.control',
     'Tell us what worked',
     'When an agent shows you something useful — or something wrong — use the feedback control to flag it. Your feedback shapes how the system improves over time.'),

    ('finish', 'user', 60, 'none', NULL,
     'You''re all set',
     'You can replay this tour any time from the sidebar. Happy chatting!')

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
