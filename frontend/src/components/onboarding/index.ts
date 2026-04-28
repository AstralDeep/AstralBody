// Barrel for the onboarding feature (005-tooltips-tutorial).
// Re-export the public surface used by DashboardLayout and DynamicRenderer.

export { OnboardingProvider, useOnboarding } from './OnboardingContext';
export { TutorialOverlay } from './TutorialOverlay';
export { TooltipProvider } from './TooltipProvider';
export { Tooltip } from './Tooltip';
export { TutorialAdminPanel } from './TutorialAdminPanel';
export { tooltipCatalog } from './tooltipCatalog';
export type { OnboardingState, TutorialStep } from './types';
