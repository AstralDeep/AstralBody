/**
 * US-21: Audio primitive rendering tests.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { FeedbackProvider } from '../feedback/FeedbackContext';
import DynamicRenderer from '../DynamicRenderer';

// ---------------------------------------------------------------------------
// Mock framer-motion (same pattern as SDUICanvas.flash.test.tsx)
// ---------------------------------------------------------------------------
type MotionPropsLike = Record<string, unknown> & {
    initial?: unknown;
    children?: React.ReactNode;
};

vi.mock("framer-motion", () => {
    const cache = new Map<string, React.ComponentType<MotionPropsLike>>();
    const passthrough = (tag: string) => {
        const cached = cache.get(tag);
        if (cached) return cached;
        const C = React.forwardRef<HTMLElement, MotionPropsLike>((props, ref) => {
            const {
                initial,
                animate: _animate,
                exit: _exit,
                transition: _transition,
                layout: _layout,
                whileHover: _whileHover,
                whileTap: _whileTap,
                ...rest
            } = props;
            void _animate; void _exit; void _transition; void _layout;
            void _whileHover; void _whileTap;
            const [firstInitial] = React.useState(() => initial);
            const dataInitial = firstInitial === false ? "false" : "animate";
            return React.createElement(tag, { ...rest, ref, "data-initial": dataInitial });
        });
        cache.set(tag, C as unknown as React.ComponentType<MotionPropsLike>);
        return C as unknown as React.ComponentType<MotionPropsLike>;
    };
    return {
        motion: new Proxy({} as Record<string, unknown>, {
            get: (_t, prop: string) => passthrough(prop),
        }),
        AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    };
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function renderWithProviders(ui: React.ReactElement) {
    return render(
        <FeedbackProvider token="test-token" ws={null}>
            {ui}
        </FeedbackProvider>
    );
}

// ---------------------------------------------------------------------------
describe('Audio Primitive — DynamicRenderer', () => {
    it('renders an <audio> element with source', () => {
        const comps = [{
            type: 'audio',
            src: 'https://example.com/sound.wav',
            contentType: 'audio/wav',
            showControls: true,
        }];

        renderWithProviders(<DynamicRenderer components={comps} />);
        const audio = screen.getByRole('audio') as HTMLAudioElement;
        // The <audio> element itself should be there
        expect(audio).toBeInTheDocument();
        // And it should have a <source> child
        const source = audio.querySelector('source');
        expect(source).not.toBeNull();
        expect(source!.getAttribute('src')).toBe('https://example.com/sound.wav');
    });

    it('shows label when provided', () => {
        const comps = [{
            type: 'audio',
            src: 'https://example.com/sound.wav',
            label: 'Piano Melody',
        }];

        renderWithProviders(<DynamicRenderer components={comps} />);
        expect(screen.getByText('Piano Melody')).toBeInTheDocument();
    });

    it('shows description when provided', () => {
        const comps = [{
            type: 'audio',
            src: 'https://example.com/sound.wav',
            description: 'C major arpeggio',
        }];

        renderWithProviders(<DynamicRenderer components={comps} />);
        expect(screen.getByText('C major arpeggio')).toBeInTheDocument();
    });

    it('shows fallback when src is empty', () => {
        const comps = [{
            type: 'audio',
            src: '',
        }];

        renderWithProviders(<DynamicRenderer components={comps} />);
        expect(screen.getByText('No audio source provided')).toBeInTheDocument();
    });

    it('does not render controls attribute when showControls is false', () => {
        const comps = [{
            type: 'audio',
            src: 'https://example.com/sound.wav',
            showControls: false,
        }];

        renderWithProviders(<DynamicRenderer components={comps} />);
        const audio = screen.queryByRole('audio') as HTMLAudioElement | null;
        expect(audio).toBeInTheDocument();
        expect(audio!.controls).toBe(false);
    });

    it('supports autoplay and loop attributes', () => {
        const comps = [{
            type: 'audio',
            src: 'https://example.com/sound.wav',
            autoplay: true,
            loop: true,
        }];

        renderWithProviders(<DynamicRenderer components={comps} />);
        const audio = screen.getByRole('audio') as HTMLAudioElement;
        expect(audio.autoplay).toBe(true);
        expect(audio.loop).toBe(true);
    });
});