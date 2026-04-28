/**
 * UserGuidePanel — full-screen static reference overlay for end users.
 *
 * No router in the project; this matches the existing AuditLogPanel /
 * FeedbackAdminPanel modal-overlay pattern and reflects its open state
 * in the URL via `?guide=open[&guide_section=…]` so refreshing or
 * sharing the URL restores the same view.
 *
 * The guide is intentionally static content (no live data, no fetches).
 * Sections cover every user-facing aspect of the system: signing in,
 * the dashboard, chat, agents, audit log, feedback, and the
 * getting-started tutorial.
 */
import { useEffect, useMemo, useState } from "react";
import {
    BookOpen,
    Bot,
    ChevronRight,
    Compass,
    KeyRound,
    LayoutDashboard,
    ListChecks,
    MessageSquare,
    Mic,
    Monitor,
    Paperclip,
    Pencil,
    RefreshCw,
    Search,
    Shield,
    ShieldAlert,
    Sparkles,
    UploadCloud,
    Volume2,
    X,
} from "lucide-react";

export interface UserGuidePanelProps {
    open: boolean;
    onClose: () => void;
    isAdmin?: boolean;
}

type SectionId =
    | "intro"
    | "signing-in"
    | "dashboard"
    | "chat"
    | "attachments"
    | "voice"
    | "agents"
    | "components"
    | "feedback"
    | "audit"
    | "tutorial"
    | "tooltips"
    | "preferences"
    | "device"
    | "privacy"
    | "admin";

interface Section {
    id: SectionId;
    label: string;
    icon: React.ReactNode;
    adminOnly?: boolean;
}

const SECTIONS: Section[] = [
    { id: "intro", label: "Welcome", icon: <BookOpen size={14} /> },
    { id: "signing-in", label: "Signing in", icon: <KeyRound size={14} /> },
    { id: "dashboard", label: "Dashboard tour", icon: <LayoutDashboard size={14} /> },
    { id: "chat", label: "Chatting with agents", icon: <MessageSquare size={14} /> },
    { id: "attachments", label: "Attachments & files", icon: <Paperclip size={14} /> },
    { id: "voice", label: "Voice in & out", icon: <Mic size={14} /> },
    { id: "agents", label: "Browsing agents", icon: <Bot size={14} /> },
    { id: "components", label: "Saved components", icon: <Sparkles size={14} /> },
    { id: "feedback", label: "Giving feedback", icon: <MessageSquare size={14} /> },
    { id: "audit", label: "Your audit log", icon: <ListChecks size={14} /> },
    { id: "tutorial", label: "Getting-started tour", icon: <Compass size={14} /> },
    { id: "tooltips", label: "Tooltips & hints", icon: <Sparkles size={14} /> },
    { id: "preferences", label: "Theme & preferences", icon: <Monitor size={14} /> },
    { id: "device", label: "Mobile, tablet & touch", icon: <RefreshCw size={14} /> },
    { id: "privacy", label: "Privacy & per-user data", icon: <Shield size={14} /> },
    { id: "admin", label: "For administrators", icon: <ShieldAlert size={14} />, adminOnly: true },
];

function readSectionFromUrl(): SectionId {
    if (typeof window === "undefined") return "intro";
    const v = new URLSearchParams(window.location.search).get("guide_section");
    if (!v) return "intro";
    const valid = SECTIONS.some((s) => s.id === v);
    return valid ? (v as SectionId) : "intro";
}

function writeSectionToUrl(section: SectionId, open: boolean) {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (open) {
        params.set("guide", "open");
        params.set("guide_section", section);
    } else {
        params.delete("guide");
        params.delete("guide_section");
    }
    const qs = params.toString();
    const url = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
    window.history.replaceState({}, "", url);
}

export default function UserGuidePanel({ open, onClose, isAdmin = false }: UserGuidePanelProps) {
    const [section, setSection] = useState<SectionId>(() => readSectionFromUrl());
    const [query, setQuery] = useState<string>("");

    useEffect(() => {
        writeSectionToUrl(section, open);
    }, [section, open]);

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, [open, onClose]);

    const visibleSections = useMemo(() => {
        const all = SECTIONS.filter((s) => !s.adminOnly || isAdmin);
        if (!query.trim()) return all;
        const q = query.toLowerCase();
        return all.filter((s) => s.label.toLowerCase().includes(q));
    }, [query, isAdmin]);

    if (!open) return null;

    return (
        <div
            role="dialog"
            aria-modal="true"
            aria-label="User guide"
            className="fixed inset-0 z-[10003] bg-black/70 flex items-center justify-center p-4"
        >
            <div className="bg-astral-bg border border-white/10 rounded-xl shadow-2xl
                            w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
                    <div className="flex items-center gap-2 text-white">
                        <BookOpen size={18} className="text-astral-primary" />
                        <strong>User guide</strong>
                        <span className="text-xs text-astral-muted hidden md:inline">
                            Everything you can do in AstralBody
                        </span>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="text-astral-muted hover:text-white p-1.5 rounded-md hover:bg-white/5"
                    >
                        <X size={16} />
                    </button>
                </div>

                <div className="flex-1 flex flex-col md:flex-row min-h-0">
                    {/* Sidebar / table of contents */}
                    <aside className="w-full md:w-64 border-b md:border-b-0 md:border-r border-white/10
                                      flex-shrink-0 overflow-y-auto p-3">
                        <div className="flex items-center gap-1.5 bg-white/5 border border-white/5
                                        rounded-lg px-2 py-1.5 mb-3
                                        focus-within:border-astral-primary/30">
                            <Search size={12} className="text-astral-muted/60 flex-shrink-0" />
                            <input
                                type="text"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search the guide…"
                                className="bg-transparent text-xs text-white placeholder:text-astral-muted/40
                                           focus:outline-none w-full"
                                autoComplete="off"
                            />
                        </div>
                        <nav className="space-y-0.5">
                            {visibleSections.map((s) => (
                                <button
                                    key={s.id}
                                    onClick={() => setSection(s.id)}
                                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md
                                                text-xs text-left transition-colors group
                                                ${section === s.id
                                                    ? "bg-astral-primary/15 text-white"
                                                    : "text-astral-muted hover:text-white hover:bg-white/5"}`}
                                >
                                    <span className="text-astral-primary/80">{s.icon}</span>
                                    <span className="flex-1">{s.label}</span>
                                    {section === s.id && (
                                        <ChevronRight size={12} className="text-astral-primary" />
                                    )}
                                </button>
                            ))}
                        </nav>
                    </aside>

                    {/* Content */}
                    <main className="flex-1 overflow-y-auto p-6 md:p-8 text-white">
                        <Article section={section} isAdmin={isAdmin} />
                    </main>
                </div>
            </div>
        </div>
    );
}

// ────────────────────────────────────────────────────────────────────────────
// Article content
// ────────────────────────────────────────────────────────────────────────────

function Article({ section, isAdmin }: { section: SectionId; isAdmin: boolean }) {
    switch (section) {
        case "intro":
            return <IntroSection />;
        case "signing-in":
            return <SigningInSection />;
        case "dashboard":
            return <DashboardSection />;
        case "chat":
            return <ChatSection />;
        case "attachments":
            return <AttachmentsSection />;
        case "voice":
            return <VoiceSection />;
        case "agents":
            return <AgentsSection />;
        case "components":
            return <ComponentsSection />;
        case "feedback":
            return <FeedbackSection />;
        case "audit":
            return <AuditSection />;
        case "tutorial":
            return <TutorialSection />;
        case "tooltips":
            return <TooltipsSection />;
        case "preferences":
            return <PreferencesSection />;
        case "device":
            return <DeviceSection />;
        case "privacy":
            return <PrivacySection />;
        case "admin":
            return isAdmin ? <AdminSection /> : <IntroSection />;
        default:
            return <IntroSection />;
    }
}

// Reusable styling helpers
function H1({ children }: { children: React.ReactNode }) {
    return <h1 className="text-2xl font-semibold mb-3 leading-tight">{children}</h1>;
}
function H2({ children }: { children: React.ReactNode }) {
    return (
        <h2 className="text-base font-semibold mt-6 mb-2 text-white/90 border-b border-white/5 pb-1">
            {children}
        </h2>
    );
}
function P({ children }: { children: React.ReactNode }) {
    return <p className="text-sm text-astral-muted leading-relaxed mb-3">{children}</p>;
}
function UL({ children }: { children: React.ReactNode }) {
    return (
        <ul className="text-sm text-astral-muted leading-relaxed mb-3 list-disc pl-5 space-y-1">
            {children}
        </ul>
    );
}
function Kbd({ children }: { children: React.ReactNode }) {
    return (
        <kbd className="bg-white/5 border border-white/10 rounded px-1.5 py-0.5 text-[10px]
                        font-mono text-white">
            {children}
        </kbd>
    );
}
function Strong({ children }: { children: React.ReactNode }) {
    return <strong className="text-white">{children}</strong>;
}
function Tip({ children }: { children: React.ReactNode }) {
    return (
        <div className="my-3 border border-astral-primary/20 bg-astral-primary/5 rounded-lg p-3
                        text-sm text-astral-muted leading-relaxed">
            <div className="flex items-start gap-2">
                <Sparkles size={14} className="text-astral-primary mt-0.5 flex-shrink-0" />
                <div>{children}</div>
            </div>
        </div>
    );
}

// ────────────────────────────────────────────────────────────────────────────
// Sections
// ────────────────────────────────────────────────────────────────────────────

function IntroSection() {
    return (
        <>
            <H1>Welcome to AstralBody</H1>
            <P>
                AstralBody is a chat-first workspace where you collaborate with intelligent
                agents that can use tools, look things up, run small tasks, and render rich
                interactive components back to you. Everything an agent does on your behalf
                is recorded in your private audit log so you can verify what happened.
            </P>
            <P>
                This guide explains every part of the dashboard you'll use day to day. Use
                the table of contents on the left, or search for a topic. Press{" "}
                <Kbd>Esc</Kbd> at any time to close this guide.
            </P>
            <H2>How to use this guide</H2>
            <UL>
                <li>
                    <Strong>New here?</Strong> Start with{" "}
                    <em>Signing in</em>, then <em>Dashboard tour</em>, then{" "}
                    <em>Chatting with agents</em>.
                </li>
                <li>
                    <Strong>Want a hands-on walkthrough?</Strong> Use the{" "}
                    <em>Take the tour</em> button in the sidebar to launch the
                    interactive getting-started tour.
                </li>
                <li>
                    <Strong>Looking for something specific?</Strong> Search the
                    table of contents, or hover any control on the dashboard for a
                    short tooltip.
                </li>
            </UL>
        </>
    );
}

function SigningInSection() {
    return (
        <>
            <H1>Signing in</H1>
            <P>
                AstralBody uses your organisation's single sign-on (SSO) provider. When you
                visit the site you'll be redirected to the sign-in page; after you
                authenticate, you're returned to the dashboard.
            </P>
            <H2>Roles</H2>
            <UL>
                <li>
                    <Strong>User</Strong> — chat with agents, give feedback, view your own
                    audit log, replay the tutorial.
                </li>
                <li>
                    <Strong>Admin</Strong> — everything users can do, plus the admin panels
                    (tool quality, knowledge proposals, quarantine, tutorial editor).
                </li>
            </UL>
            <P>
                If you sign in but see an "Unauthorized access" page, your account doesn't
                have either role yet — contact an administrator.
            </P>
            <H2>Signing out</H2>
            <P>
                Click the <Strong>Sign out</Strong> button at the bottom of the sidebar.
                Your session ends both in AstralBody and at your SSO provider.
            </P>
        </>
    );
}

function DashboardSection() {
    return (
        <>
            <H1>Dashboard tour</H1>
            <P>
                The dashboard is split into a sidebar on the left and the main canvas on
                the right. The chat panel floats over the canvas; you can drag and resize
                it.
            </P>
            <H2>Sidebar</H2>
            <UL>
                <li>
                    <Strong>New chat</Strong> — start a fresh conversation. Existing chats
                    appear under <em>Recent Chats</em> for quick switching.
                </li>
                <li>
                    <Strong>Status</Strong> — shows whether the orchestrator is connected,
                    how many agents are active, and the total number of tools available.
                </li>
                <li>
                    <Strong>Agents</Strong> — opens the agents panel where you can browse,
                    grant scopes, and configure credentials.
                </li>
                <li>
                    <Strong>Audit log</Strong> — your private record of every action an
                    agent has taken on your behalf.
                </li>
                <li>
                    <Strong>Take the tour</Strong> — replays the guided tutorial overlay.
                </li>
                <li>
                    <Strong>Tutorial admin</Strong> — admins only; edit the tutorial step
                    copy live (see <em>For administrators</em>).
                </li>
                <li>
                    <Strong>Tool quality</Strong> — admins only; review flagged tools,
                    knowledge proposals, and quarantined feedback.
                </li>
                <li>
                    <Strong>Sign out</Strong> — at the bottom of the sidebar.
                </li>
            </UL>
            <Tip>
                Hover any sidebar entry for ~½ second to see a short tooltip describing
                what it does. The same tooltips appear when you Tab through the controls
                with the keyboard.
            </Tip>
            <H2>Main canvas</H2>
            <P>
                When agents render rich components — tables, charts, file downloads,
                forms — they appear on the canvas. You can save individual components for
                later, combine or condense groups of them, and provide feedback on each
                one.
            </P>
            <H2>Floating chat</H2>
            <P>
                The chat panel is your primary input. Drag its title bar to move it,
                drag any edge to resize it, and click the chevron to collapse it to a
                strip. The position and size are remembered for next time.
            </P>
        </>
    );
}

function ChatSection() {
    return (
        <>
            <H1>Chatting with agents</H1>
            <P>
                Type a message in the chat input and press <Kbd>Enter</Kbd> (or click the
                send button) to start a conversation. Behind the scenes, the orchestrator
                routes your request to the right agent, which may run several tools to
                build its answer.
            </P>
            <H2>What you can ask</H2>
            <UL>
                <li>
                    <Strong>Questions</Strong> — agents will use search, lookup, and
                    knowledge tools to answer.
                </li>
                <li>
                    <Strong>Tasks</Strong> — "summarise this PDF", "draft an email",
                    "render a chart of …".
                </li>
                <li>
                    <Strong>Follow-ups</Strong> — every chat keeps context, so you can
                    refine without restating everything.
                </li>
            </UL>
            <H2>While the agent is thinking</H2>
            <P>
                A status indicator shows the current step — searching, calling a tool,
                rendering output. You can press the <Strong>Cancel</Strong> button to
                stop a long-running task at any time.
            </P>
            <H2>Multiple chats</H2>
            <P>
                Click <Strong>+ New chat</Strong> in the sidebar to start a new
                conversation. Switch between chats by clicking them under{" "}
                <em>Recent Chats</em>. Each chat is independent — agents can't see other
                chats' history. Delete a chat from its overflow menu.
            </P>
        </>
    );
}

function AttachmentsSection() {
    return (
        <>
            <H1>Attachments & files</H1>
            <P>
                Click the <Paperclip size={12} className="inline -mt-0.5" /> icon next to
                the chat input to attach files to a message. AstralBody supports common
                document, image, and data formats up to 30 MB per file. Files are stored
                privately to your account and persist across chats — you can re-use an
                attachment from the library without re-uploading.
            </P>
            <H2>Attachment library</H2>
            <P>
                Open the attachment library to see every file you've uploaded, when, and
                what type it is. Files you delete from the library are removed from
                future use, but historical chats that referenced them still record the
                fact (without the bytes) in your audit log.
            </P>
            <H2>Files an agent gives you</H2>
            <P>
                When an agent generates a file (a CSV, an image, a PDF), the canvas shows
                a download component with a button. Click <Strong>Download</Strong> to
                save it locally. The orchestrator records the download in your audit log.
            </P>
            <Tip>
                Don't attach files containing secrets you wouldn't want logged.
                AstralBody redacts known PHI/PII patterns from audit-event metadata, but
                the safest data is data you never upload.
            </Tip>
        </>
    );
}

function VoiceSection() {
    return (
        <>
            <H1>Voice in & out</H1>
            <P>
                If your device exposes a microphone, the <Mic size={12} className="inline -mt-0.5" />{" "}
                button next to the chat input lets you dictate a message instead of typing.
                You'll see a live transcript while you speak; press the stop icon when
                you're done. Your speech is sent to the orchestrator for transcription and
                does not leave your audit log unaudited.
            </P>
            <H2>Spoken responses</H2>
            <P>
                Toggle the <Volume2 size={12} className="inline -mt-0.5" /> button to have
                the agent's text response read aloud. The toggle remembers its setting
                between sessions.
            </P>
            <P>
                Voice is optional and gracefully disabled on devices without microphone
                or audio support.
            </P>
        </>
    );
}

function AgentsSection() {
    return (
        <>
            <H1>Browsing agents</H1>
            <P>
                Open the <Strong>Agents</Strong> panel from the sidebar to see every
                agent the orchestrator can route requests to. Each agent advertises a
                set of <em>tools</em> — small functions it can call — and a set of{" "}
                <em>scopes</em> that gate which categories of tools you've granted it.
            </P>
            <H2>Three tabs</H2>
            <UL>
                <li>
                    <Strong>My agents</Strong> — agents you own or have configured.
                </li>
                <li>
                    <Strong>All agents</Strong> — every agent registered with the
                    orchestrator, including public ones from other users.
                </li>
                <li>
                    <Strong>Drafts</Strong> — agents you've created but not yet finalised.
                    Click a draft to resume editing it.
                </li>
            </UL>
            <H2>Permissions</H2>
            <P>
                Click an agent to open its permissions modal. Toggle each scope on or
                off; for finer control, override individual tools within an enabled
                scope. Changes save instantly and apply to your account only — they
                don't affect other users' permissions for the same agent.
            </P>
            <H2>Credentials</H2>
            <P>
                Some agents need external API keys (e.g. for a third-party service). The
                permissions modal shows which keys an agent expects and lets you save
                them encrypted server-side, or kick off an OAuth flow when supported.
            </P>
            <H2>Public vs. private</H2>
            <P>
                If you own an agent, you can toggle it public or private from the
                permissions modal. Public agents appear in <em>All agents</em> for every
                user; private ones are visible only to you.
            </P>
            <H2>Creating a new agent</H2>
            <P>
                Click <Strong>+ Create agent</Strong> in the agents panel to describe a
                new agent in plain language. The system generates the code, packages,
                and skill tags, and submits the draft for security review. You can
                resume or delete drafts from the <em>Drafts</em> tab.
            </P>
        </>
    );
}

function ComponentsSection() {
    return (
        <>
            <H1>Saved components</H1>
            <P>
                When an agent renders something useful — a table of results, a chart,
                a metric card — you can pin it for later. Hover a component to surface
                the <Strong>Save</Strong> button.
            </P>
            <H2>Where saved items live</H2>
            <P>
                Click the saved-components drawer to see everything you've pinned, grouped
                by chat. From there you can re-open the originating chat, delete an item,
                or combine several into a single condensed view.
            </P>
            <H2>Combine & condense</H2>
            <UL>
                <li>
                    <Strong>Combine</Strong> — selects multiple saved components and asks
                    the orchestrator to merge them into a single richer component.
                </li>
                <li>
                    <Strong>Condense</Strong> — produces a shorter summary version of a
                    long or noisy component.
                </li>
            </UL>
        </>
    );
}

function FeedbackSection() {
    return (
        <>
            <H1>Giving feedback</H1>
            <P>
                Every component an agent renders has a small{" "}
                <Strong>feedback control</Strong> (a 💬 icon) you can use to tell us
                whether it was useful. Your feedback shapes how the system improves over
                time and helps administrators identify underperforming tools.
            </P>
            <H2>How it works</H2>
            <UL>
                <li>
                    <Strong>Thumbs up</Strong> — record that this component was useful.
                </li>
                <li>
                    <Strong>Thumbs down</Strong> — flag the component, optionally with a
                    category (wrong data, irrelevant, layout broken, too slow) and a
                    short comment.
                </li>
            </UL>
            <H2>Privacy</H2>
            <P>
                Your feedback is associated with your account and the specific component
                you rated. Comments are scanned for unsafe content; flagged comments are
                quarantined for admin review and don't influence the system's learning
                until released.
            </P>
            <H2>Editing or retracting</H2>
            <P>
                Within 24 hours of submitting, you can amend or retract a feedback entry.
                After that window, the original record is preserved (with a new amendment
                record if you change it).
            </P>
        </>
    );
}

function AuditSection() {
    return (
        <>
            <H1>Your audit log</H1>
            <P>
                The audit log records every action an agent takes on your behalf, every
                tool call, every file download, and every authentication event. It is
                strictly per-user — you only ever see your own entries, and not even
                administrators can read them through the UI.
            </P>
            <H2>What you'll see</H2>
            <UL>
                <li>
                    <Strong>Action type</Strong> — the operation (e.g. <code>auth.login</code>,{" "}
                    <code>agent.tool_call</code>, <code>file.download</code>).
                </li>
                <li>
                    <Strong>Outcome</Strong> — in progress, success, failure, or
                    interrupted.
                </li>
                <li>
                    <Strong>Description</Strong> — a short human-readable summary.
                </li>
                <li>
                    <Strong>Inputs / outputs metadata</Strong> — non-sensitive context
                    (e.g. tool name, file extension, conversation id) — never the raw
                    payload.
                </li>
                <li>
                    <Strong>Artifact pointers</Strong> — links to the underlying file or
                    chat the row references; click to open if still available.
                </li>
                <li>
                    <Strong>Recorded at</Strong> — server-side timestamp.
                </li>
            </UL>
            <H2>Filtering & search</H2>
            <P>
                Use the filter chips to narrow by event class (auth, conversation, tool
                call, file, settings) or outcome. Filters persist in the URL so refreshing
                or sharing the URL restores the same view. Live entries stream into the
                top of the list as new actions occur.
            </P>
            <H2>Detail drawer</H2>
            <P>
                Click any row to open a detail drawer with full metadata, correlated
                paired entries (a tool call typically has an{" "}
                <code>in_progress</code> followed by a <code>success</code> or{" "}
                <code>failure</code>), and the artifact pointers.
            </P>
            <Tip>
                The audit log is append-only and signed. If you ever need to verify
                integrity over time, support staff can run an offline chain-verification
                check; the result is cryptographic, not just visual.
            </Tip>
        </>
    );
}

function TutorialSection() {
    return (
        <>
            <H1>Getting-started tour</H1>
            <P>
                The first time you sign in, AstralBody walks you through the core
                workflow as a guided overlay: starting a chat, opening agents, reviewing
                the audit log, and giving feedback. The overlay highlights the relevant
                control on the dashboard for each step.
            </P>
            <H2>Controls</H2>
            <UL>
                <li>
                    <Strong>Next / Back</Strong> — advance or go back through the steps.
                </li>
                <li>
                    <Strong>Skip tour</Strong> or <Kbd>Esc</Kbd> — close the overlay; the
                    system remembers you skipped and won't auto-launch again.
                </li>
                <li>
                    <Strong>Replay</Strong> — open the sidebar's <em>Take the tour</em>{" "}
                    entry to relaunch the overlay any time.
                </li>
            </UL>
            <H2>Resume on reload</H2>
            <P>
                If you refresh the browser part-way through the tour, you resume on the
                same step (or the next still-applicable step if a step has been
                archived). State follows your account, so signing in from a different
                device or browser preserves your progress.
            </P>
            <H2>Admins see extra steps</H2>
            <P>
                Admin users see the same user-flow tour with admin-specific steps
                appended at the end (covering the feedback admin surfaces and the
                tutorial editor).
            </P>
        </>
    );
}

function TooltipsSection() {
    return (
        <>
            <H1>Tooltips & hints</H1>
            <P>
                Almost every interactive control on the dashboard has a contextual
                tooltip. Tooltips reduce trial-and-error — hover or keyboard-focus a
                control to learn what it does without opening this guide.
            </P>
            <H2>How to trigger a tooltip</H2>
            <UL>
                <li>
                    <Strong>Mouse</Strong> — hover the control for ~500 ms.
                </li>
                <li>
                    <Strong>Keyboard</Strong> — press <Kbd>Tab</Kbd> until the control is
                    focused; the tooltip appears immediately.
                </li>
                <li>
                    <Strong>Touch</Strong> — long-press the control.
                </li>
                <li>
                    Press <Kbd>Esc</Kbd> at any time to dismiss the active tooltip.
                </li>
            </UL>
            <H2>Server-rendered tooltips</H2>
            <P>
                Some components an agent renders carry their own tooltip text from the
                backend — usually for buttons or actions inside a complex card. They
                behave the same as static-UI tooltips.
            </P>
            <Tip>
                If a control doesn't show a tooltip, it doesn't have help text — that's
                intentional, not a bug. Empty tooltip frames are never displayed.
            </Tip>
        </>
    );
}

function PreferencesSection() {
    return (
        <>
            <H1>Theme & preferences</H1>
            <P>
                AstralBody adapts to your operating-system colour preference by default,
                and remembers any explicit override per account. The dashboard also
                stores small preferences like sidebar collapsed/expanded and the
                floating-chat panel size on your account so they follow you across
                devices.
            </P>
            <H2>Resetting</H2>
            <P>
                Click <Strong>Sign out</Strong> and back in to re-fetch preferences from
                the server. Local-only state (e.g. unsubmitted draft messages) is
                discarded on sign-out.
            </P>
        </>
    );
}

function DeviceSection() {
    return (
        <>
            <H1>Mobile, tablet & touch</H1>
            <P>
                The dashboard reflows to smaller viewports automatically. The sidebar
                slides off-screen by default on mobile; tap the menu icon to bring it
                back. The floating-chat panel uses your full screen width on small
                devices.
            </P>
            <H2>Touch interactions</H2>
            <UL>
                <li>
                    <Strong>Tooltips</Strong> appear on long-press instead of hover.
                </li>
                <li>
                    <Strong>Tutorial overlay</Strong> uses tap to advance, tap-and-hold
                    on the X to skip — no hover required.
                </li>
                <li>
                    <Strong>Voice input</Strong> works wherever the device microphone is
                    available.
                </li>
            </UL>
            <H2>Cross-device sync</H2>
            <P>
                Anything stored on the backend — chats, audit log, onboarding progress,
                feedback, agent permissions — follows your account across browsers and
                devices. Local UI state (panel sizes, toast positions) is per-device.
            </P>
        </>
    );
}

function PrivacySection() {
    return (
        <>
            <H1>Privacy & per-user data</H1>
            <P>
                AstralBody is built around strict per-user isolation. Every data store
                that touches your activity — chats, files, audit events, feedback,
                onboarding state — is scoped to your account at the API layer. There is
                no UI path through which one user can read another user's data, and even
                administrators cannot read your audit log through the dashboard.
            </P>
            <H2>What is logged</H2>
            <UL>
                <li>
                    <Strong>Recorded</Strong> — non-sensitive metadata (action type,
                    timestamps, tool name, outcome, file extension, identifiers).
                </li>
                <li>
                    <Strong>Not recorded</Strong> — raw message bodies, file contents,
                    secrets, or personally identifying information that can be redacted.
                </li>
            </UL>
            <H2>Retention</H2>
            <P>
                Audit events are retained for compliance for several years and are then
                purged by an offline operator job (never the dashboard). File
                attachments persist until you delete them from the library.
            </P>
            <H2>Reporting a problem</H2>
            <P>
                If you see something that looks like a privacy leak — a row in your
                audit log that shouldn't be yours, a tooltip showing private text — flag
                it via the feedback control on the affected component and contact your
                administrator immediately.
            </P>
        </>
    );
}

function AdminSection() {
    return (
        <>
            <H1>For administrators</H1>
            <P>
                Admins see two extra surfaces in the sidebar:
            </P>
            <H2>
                <Pencil size={14} className="inline -mt-0.5 mr-1" />
                Tutorial admin
            </H2>
            <P>
                Edit the copy of every step in the getting-started tour without a code
                change. New, edited, archived, and restored steps take effect on the
                next user replay.
            </P>
            <UL>
                <li>
                    <Strong>New step</Strong> — create a step with a stable slug,
                    audience (user or admin), display order, and target.
                </li>
                <li>
                    <Strong>Edit</Strong> — partial updates write a revision row with
                    full before/after snapshots.
                </li>
                <li>
                    <Strong>Archive / Restore</Strong> — soft-delete keeps revision
                    history intact and lets in-flight users resume safely.
                </li>
                <li>
                    <Strong>Revisions</Strong> — every change records who, when, and
                    what; the audit log records a structured changed-fields summary.
                </li>
            </UL>
            <H2>
                <UploadCloud size={14} className="inline -mt-0.5 mr-1" />
                Tool quality
            </H2>
            <UL>
                <li>
                    <Strong>Flagged tools</Strong> — tools whose recent quality signals
                    have crossed the underperformance threshold. Click for evidence.
                </li>
                <li>
                    <Strong>Proposals</Strong> — system-generated knowledge-update
                    proposals; accept (optionally with edits) or reject with a rationale.
                    Applied changes write to <code>backend/knowledge/</code> atomically.
                </li>
                <li>
                    <Strong>Quarantine</Strong> — feedback flagged for unsafe content.
                    Release back into the synthesizer pool or dismiss.
                </li>
            </UL>
            <H2>What admins still cannot do via the UI</H2>
            <UL>
                <li>Read another user's audit log entries.</li>
                <li>Read another user's onboarding state.</li>
                <li>Read another user's saved files.</li>
            </UL>
            <P>
                These are operator-only operations and require a server-side CLI under a
                separate authority.
            </P>
        </>
    );
}
