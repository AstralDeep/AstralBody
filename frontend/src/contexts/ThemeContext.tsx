import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from "react";

export interface ThemeColors {
    bg: string;
    surface: string;
    primary: string;
    secondary: string;
    text: string;
    muted: string;
    accent: string;
}

export const THEME_PRESETS: Record<string, ThemeColors> = {
    midnight: {
        bg: "#0F1221", surface: "#1A1E2E", primary: "#6366F1",
        secondary: "#8B5CF6", text: "#F3F4F6", muted: "#9CA3AF", accent: "#06B6D4",
    },
    daylight: {
        bg: "#F8FAFC", surface: "#FFFFFF", primary: "#4F46E5",
        secondary: "#7C3AED", text: "#1E293B", muted: "#64748B", accent: "#0891B2",
    },
    ocean: {
        bg: "#0C1222", surface: "#132038", primary: "#0EA5E9",
        secondary: "#06B6D4", text: "#E2E8F0", muted: "#94A3B8", accent: "#2DD4BF",
    },
    sunset: {
        bg: "#1C1017", surface: "#2D1B24", primary: "#F97316",
        secondary: "#EF4444", text: "#FEF2F2", muted: "#A8A29E", accent: "#FBBF24",
    },
    forest: {
        bg: "#0F1A14", surface: "#1A2E22", primary: "#22C55E",
        secondary: "#10B981", text: "#ECFDF5", muted: "#86EFAC", accent: "#A3E635",
    },
};

interface ThemeContextValue {
    colors: ThemeColors;
    themeName: string;
    setTheme: (name: string) => void;
    setColor: (key: keyof ThemeColors, hex: string) => void;
    setColors: (colors: ThemeColors) => void;
    presets: Record<string, ThemeColors>;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = "astral-theme";
const STORAGE_NAME_KEY = "astral-theme-name";

function hexToRgbChannels(hex: string): string {
    const h = hex.replace("#", "");
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `${r} ${g} ${b}`;
}

function applyTheme(colors: ThemeColors) {
    const root = document.documentElement;
    for (const [key, hex] of Object.entries(colors)) {
        root.style.setProperty(`--astral-${key}`, hexToRgbChannels(hex));
    }
}

function loadStoredTheme(): { colors: ThemeColors; name: string } {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        const name = localStorage.getItem(STORAGE_NAME_KEY) || "midnight";
        if (stored) {
            const parsed = JSON.parse(stored) as ThemeColors;
            if (parsed.bg && parsed.primary && parsed.text) {
                return { colors: parsed, name };
            }
        }
    } catch { /* ignore */ }
    return { colors: THEME_PRESETS.midnight, name: "midnight" };
}

function isValidThemeColors(obj: unknown): obj is ThemeColors {
    if (!obj || typeof obj !== "object") return false;
    const o = obj as Record<string, unknown>;
    return typeof o.bg === "string" && typeof o.primary === "string" && typeof o.text === "string";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
    const [colors, setColorsState] = useState<ThemeColors>(() => loadStoredTheme().colors);
    const [themeName, setThemeName] = useState(() => loadStoredTheme().name);
    const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const serverLoadedRef = useRef(false);

    // Apply CSS variables whenever colors change
    useEffect(() => {
        applyTheme(colors);
    }, [colors]);

    // Persist to localStorage whenever colors/name change
    useEffect(() => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(colors));
        localStorage.setItem(STORAGE_NAME_KEY, themeName);
    }, [colors, themeName]);

    // Debounced save to server via CustomEvent
    useEffect(() => {
        // Skip the initial mount and server-load to avoid echoing back
        if (!serverLoadedRef.current && themeName === loadStoredTheme().name) return;

        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        saveTimerRef.current = setTimeout(() => {
            window.dispatchEvent(new CustomEvent("astral-save-theme", {
                detail: { colors, name: themeName },
            }));
        }, 1000);

        return () => {
            if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        };
    }, [colors, themeName]);

    // Listen for server-sent preferences (theme loaded from user profile)
    useEffect(() => {
        const onServerPreferences = (e: Event) => {
            const prefs = (e as CustomEvent).detail as Record<string, unknown> | null;
            if (!prefs?.theme) return;
            const themeData = prefs.theme as Record<string, unknown>;
            const serverColors = themeData.colors;
            const serverName = themeData.name as string | undefined;

            if (isValidThemeColors(serverColors)) {
                serverLoadedRef.current = true;
                setColorsState(serverColors);
                setThemeName(serverName || "custom");
            }
        };
        window.addEventListener("astral-server-preferences", onServerPreferences);
        return () => window.removeEventListener("astral-server-preferences", onServerPreferences);
    }, []);

    const setTheme = useCallback((name: string) => {
        const preset = THEME_PRESETS[name];
        if (preset) {
            serverLoadedRef.current = true;
            setColorsState(preset);
            setThemeName(name);
        }
    }, []);

    const setColor = useCallback((key: keyof ThemeColors, hex: string) => {
        serverLoadedRef.current = true;
        setColorsState(prev => ({ ...prev, [key]: hex }));
        setThemeName("custom");
    }, []);

    const setColors = useCallback((newColors: ThemeColors) => {
        serverLoadedRef.current = true;
        setColorsState(newColors);
        const matchingPreset = Object.entries(THEME_PRESETS).find(
            ([, preset]) => Object.entries(preset).every(([k, v]) => newColors[k as keyof ThemeColors] === v)
        );
        setThemeName(matchingPreset ? matchingPreset[0] : "custom");
    }, []);

    return (
        <ThemeContext.Provider value={{ colors, themeName, setTheme, setColor, setColors, presets: THEME_PRESETS }}>
            {children}
        </ThemeContext.Provider>
    );
}

export function useTheme(): ThemeContextValue {
    const ctx = useContext(ThemeContext);
    if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
    return ctx;
}
