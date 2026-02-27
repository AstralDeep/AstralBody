# Flutter Frontend Migration Implementation Plan

## Project Overview
Migrate the existing React frontend (`frontend/`) to Flutter (`flutter/`) with 1:1 feature and visual parity.

**Source:** `frontend/` (absolute source of truth for logic and styling)
**Target:** `flutter/flutter_frontend/` (all new code goes here)
**Backend:** `backend/` (strictly read-only, use existing API endpoints)

## Technical Strategy
- **State Management:** Riverpod (replacing Redux/Context)
- **Routing:** GoRouter (to match React Router paths)
- **Networking:** Dio (matching Axios/Fetch configurations)
- **Styling:** Flutter Material 3 with custom themes matching CSS/Tailwind values

## Flutter Project Structure (Clean Architecture)
```
flutter_frontend/
├── lib/
│   ├── core/
│   │   ├── constants/          # App constants, theme, colors
│   │   ├── utils/             # Helper functions, extensions
│   │   ├── widgets/           # Reusable base widgets
│   │   └── errors/            # Error handling, exceptions
│   ├── data/
│   │   ├── models/            # Data models (DTOs, entities)
│   │   ├── repositories/      # Data repositories
│   │   ├── datasources/       # Local & remote data sources
│   │   └── mappers/           # Model mappers
│   ├── domain/
│   │   ├── entities/          # Business entities
│   │   ├── repositories/      # Repository interfaces
│   │   └── usecases/          # Business logic use cases
│   ├── presentation/
│   │   ├── pages/             # Screen widgets
│   │   ├── widgets/           # Presentation widgets
│   │   ├── providers/         # Riverpod providers
│   │   ├── notifiers/         # State notifiers
│   │   └── router/            # GoRouter configuration
│   └── main.dart              # App entry point
├── assets/
│   ├── images/                # App images (AstralDeep.png, etc.)
│   ├── fonts/                 # Custom fonts (Inter, JetBrains Mono)
│   └── icons/                 # App icons
├── test/                      # Unit & widget tests
└── pubspec.yaml               # Dependencies
```

## Phase 1: Foundation

### 1.1 Project Scaffolding
- [ ] Create Flutter project in `flutter/flutter_frontend/`
- [ ] Set up project structure (clean architecture)
- [ ] Configure `pubspec.yaml` with dependencies:
  - `riverpod` for state management
  - `go_router` for navigation
  - `dio` for HTTP client
  - `web_socket_channel` for WebSocket
  - `flutter_secure_storage` for token storage
  - `flutter_dotenv` for environment variables
  - `intl` for localization
  - `url_launcher` for external links
  - `file_picker` for file uploads
  - `permission_handler` for permissions
  - `flutter_svg` for SVG support
  - `cached_network_image` for image caching

### 1.2 Theming & Styling
- [ ] Extract color palette from Tailwind config (`frontend/tailwind.config.js`):
  - `astral-bg: #0F1221`
  - `astral-surface: #1A1E2E`
  - `astral-primary: #6366F1`
  - `astral-secondary: #8B5CF6`
  - `astral-text: #F3F4F6`
  - `astral-muted: #9CA3AF`
  - `astral-accent: #06B6D4`
- [ ] Create Flutter `ThemeData` with Material 3 overrides
- [ ] Define custom text styles matching Inter font
- [ ] Set up dark theme as default
- [ ] Create reusable theme extensions for custom colors

### 1.3 Asset Migration
- [ ] Copy images from `frontend/public/` to `assets/images/`:
  - `AstralDeep.png` (logo)
  - `astra-fav.png` (favicon)
  - `vite.svg` (if needed)
- [ ] Set up font assets (Inter, JetBrains Mono)
- [ ] Configure `pubspec.yaml` assets section

### 1.4 Navigation Setup
- [ ] Configure GoRouter with routes:
  - `/login` - LoginScreen
  - `/dashboard` - DashboardLayout (protected)
  - `/chat/:chatId` - Chat view (optional)
- [ ] Set up route guards for authentication
- [ ] Implement deep linking support

### 1.5 Authentication Setup
- [ ] Create authentication provider with Riverpod
- [ ] Implement OIDC/Keycloak client
- [ ] Implement mock auth fallback (dev mode)
- [ ] Set up token storage (secure storage)
- [ ] Create login screen UI matching React's `LoginScreen.tsx`
- [ ] Implement role-based access control (admin/user)

## Phase 2: Networking

### 2.1 API Client
- [ ] Create Dio client with interceptors:
  - Base URL configuration (matching `frontend/src/config.ts`)
  - Authentication header injection
  - Error handling
  - Request/response logging
- [ ] Implement API service classes:
  - `AuthService` for authentication endpoints
  - `FileService` for upload/download
  - `ChatService` for chat history

### 2.2 WebSocket Client
- [ ] Create WebSocket client using `web_socket_channel`
- [ ] Implement connection management (reconnect, ping/pong)
- [ ] Map WebSocket message types from React's `useWebSocket.ts`:
  - `system_config`, `agent_registered`, `chat_status`
  - `ui_render`, `ui_update`, `ui_append`
  - `history_list`, `chat_created`, `chat_loaded`
  - `saved_components_list`, `component_saved`, `component_deleted`
  - `combine_status`, `components_combined`, `combine_error`
- [ ] Create WebSocket provider with Riverpod

### 2.3 Data Models
- [ ] Create Dart data classes mirroring React interfaces:
  - `Agent` (id, name, tools, status)
  - `ChatSession` (id, title, updated_at, preview, has_saved_components)
  - `SavedComponent` (id, chat_id, component_data, component_type, title, created_at)
  - `ChatStatus` (status, message)
  - `UIComponent` (type, properties)
- [ ] Add JSON serialization (`json_serializable`)
- [ ] Create mappers for backend responses

### 2.4 File Upload/Download
- [ ] Implement file picker for CSV/text/JSON/MD files
- [ ] Create multipart file upload to `/api/upload` endpoint
- [ ] Implement file download from `/api/download/{session_id}/{filename}`
- [ ] Add drag-and-drop support for file upload
- [ ] Create file preview functionality

## Phase 3: Components

### 3.1 Core UI Components
- [ ] **DashboardLayout** - Main app shell with sidebar and header
  - Sidebar with logo, status section, agents list, recent chats
  - Header with "New Chat" button
  - Responsive layout for mobile/desktop

- [ ] **ChatInterface** - Real-time chat with LLM agents
  - Message input with send button
  - Chat history display (user + assistant messages)
  - Loading states (thinking, executing)
  - File attachment UI with preview
  - Drag-and-drop file upload overlay

- [ ] **DynamicRenderer** - Render backend UI primitives
  - Map each component type to Flutter widget:
    - `container` → `Container`
    - `text` → `Text` with variants (h1, h2, h3, body, caption, markdown)
    - `card` → `Card` with title and content
    - `table` → `DataTable` with headers and rows
    - `metric` → Metric card with progress indicator
    - `alert` → Alert dialog with variants (info, success, warning, error)
    - `progress` → Linear progress indicator
    - `grid` → `GridView` with configurable columns
    - `list` → `ListView` with ordered/unordered variants
    - `code` → Code block with syntax highlighting
    - `bar_chart`, `line_chart`, `pie_chart` → Charts using `fl_chart` or `syncfusion_flutter_charts`
    - `plotly_chart` → WebView with Plotly.js (or native chart alternative)
    - `divider` → `Divider`
    - `button` → `ElevatedButton` with variants
    - `collapsible` → Expansion tile
    - `file_upload` → File upload button
    - `file_download` → File download button

- [ ] **UISavedDrawer** - Saved components management
  - Drawer/side panel for saved components
  - Component previews with titles
  - Delete, combine, condense operations
  - Drag-and-drop reordering

- [ ] **LoginScreen** - Authentication screen
  - SSO button for Keycloak
  - Mock auth toggle for development
  - Loading states and error messages

### 3.2 Supporting Components
- [ ] **ProgressBar** - Animated progress indicator
- [ ] **ProgressDetails** - Detailed progress display
- [ ] **ProgressDisplay** - Progress status widget
- [ ] **ComponentSaveButton** - "Add all to UI" button
- [ ] **StatusItem** - Status indicator in sidebar
- [ ] **AgentListItem** - Agent display in sidebar
- [ ] **ChatHistoryItem** - Chat session in sidebar

### 3.3 Reusable Widgets
- [ ] **GlassCard** - Glass morphism card widget
- [ ] **ShimmerEffect** - Loading shimmer animation
- [ ] **PulseGlow** - Pulsing glow animation
- [ ] **AnimatedContainer** - Framer-motion like animations
- [ ] **DragTargetOverlay** - Drag-and-drop overlay

## Phase 4: Feature Migration

### 4.1 Authentication Flow
- [ ] Implement login screen with OIDC/Keycloak integration
- [ ] Handle token validation and refresh
- [ ] Implement role checking (admin/user)
- [ ] Create unauthorized access screen
- [ ] Implement logout functionality

### 4.2 Main Dashboard
- [ ] Create dashboard with WebSocket connection
- [ ] Display connection status (connected/disconnected)
- [ ] Show agent count and tool count
- [ ] List connected agents with expandable tool lists
- [ ] Display recent chat history
- [ ] Implement "New Chat" button

### 4.3 Chat Functionality
- [ ] Send and receive chat messages via WebSocket
- [ ] Display thinking/executing/done status
- [ ] Render UI components from backend responses
- [ ] Implement file upload with drag-and-drop
- [ ] Add suggested prompts (from `SUGGESTIONS` array)
- [ ] Create file preview modal

### 4.4 Saved Components Management
- [ ] Save UI components from chat responses
- [ ] Display saved components in drawer
- [ ] Implement delete component functionality
- [ ] Implement combine components (2 components)
- [ ] Implement condense components (multiple components)
- [ ] Show combine/condense status and errors

### 4.5 Chat History Navigation
- [ ] Load chat history from backend
- [ ] Switch between chat sessions
- [ ] Persist active chat across app restarts
- [ ] Auto-generate chat titles
- [ ] Display chat preview and date

### 4.6 File Handling
- [ ] Upload files (CSV, text, JSON, MD)
- [ ] Download files from backend
- [ ] Preview file contents
- [ ] Handle large files (>10KB) via upload endpoint
- [ ] Show upload progress and errors

## Success Criteria

1. **Visual Parity**: Flutter app matches React app pixel-perfect
2. **Feature Parity**: All React features available in Flutter
3. **Performance**: 60fps animations, smooth scrolling
4. **Backend Compatibility**: Works with existing backend without modifications
5. **Platform Support**: iOS, Android, web (optional)

## Dependencies & Constraints

- Must use existing backend API endpoints exactly as defined
- Must match React's WebSocket protocol and message formats
- Must replicate exact visual design (colors, spacing, fonts)
- Must support both OIDC/Keycloak and mock authentication
- Must handle all UI component types from backend

## Open Questions

1. **Target Platforms**: Should support web/desktop in addition to mobile?
2. **Offline Capabilities**: Should app have offline functionality?
3. **Push Notifications**: Should support push notifications for chat messages?
4. **Native Device Features**: Should leverage native features (camera, GPS)?

## Next Steps

1. Review and approve this implementation plan
2. Set up Flutter development environment
3. Begin Phase 1: Foundation implementation
4. Iterate through phases with regular testing against React reference