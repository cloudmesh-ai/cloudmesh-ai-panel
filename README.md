# Cloudmesh AI Panel

The Cloudmesh AI Panel is a modern, Tailwind CSS-based admin dashboard for managing and viewing AI-powered components within the Cloudmesh AI ecosystem. It provides a unified interface to discover, activate, and analyze data from various AI extensions.

## Features

- **Zero Install Base**: The UI is a standalone HTML application using Tailwind CSS and Vue.js via CDN, requiring no build steps.
- **Component Registration**: A dedicated panel to discover and activate available AI components.
- **Unified Dashboard**: View active applications and their respective data (e.g., Git statistics, Storage equivalencies) in one place.
- **Responsive Layout**: Full-screen admin interface with a topbar, sidebar navigation, and a flexible main content area.

## Usage

The AI Panel is integrated into the Cloudmesh CLI (`cmc`).

### View the Dashboard
To start the local server and open the AI Panel in your browser:
```bash
cmc panel view
```

### Manage Applications via CLI
You can also manage the active applications in the panel directly from the command line:

**Activate an application:**
```bash
cmc panel activate --name "My AI App" --id "my-ai-app" --icon "fa-robot"
```

**Deactivate an application:**
```bash
cmc panel deactivate --id "my-ai-app"
```

**Reset all registrations:**
```bash
cmc panel reset
```

## Technical Details

- **Frontend**: HTML5, Tailwind CSS, Vue.js 3, Tabulator.js.
- **Backend**: Python `http.server` serving a dynamic HTML template and JSON APIs.
- **Configuration**: Active applications are stored in `~/.config/cloudmesh/panel/apps.json`.
## Core Dependencies
This project depends on the following core components of the Cloudmesh AI ecosystem:
- [cloudmesh-ai-common](https://github.com/cloudmesh-ai/cloudmesh-ai-common)
- [cloudmesh-ai-cmc](https://github.com/cloudmesh-ai/cloudmesh-ai-cmc)
