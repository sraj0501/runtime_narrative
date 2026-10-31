/* Single source of truth for site navigation.
   `id` must match the `data-page` attribute on each page's <body>.
   `href` is always root-relative (starts with "/"). */
window.NARRATIVE_NAV = [
  {
    group: "Showcase",
    items: [
      { id: "showcase", title: "See It In Action", href: "https://mogrov.com/wiki/runtime-narrative/showcase.html" },
    ],
  },
  {
    group: "Getting Started",
    items: [
      { id: "installation", title: "Installation", href: "https://mogrov.com/wiki/runtime-narrative/installation.html" },
      { id: "tutorial", title: "Tutorial: Your First Story", href: "https://mogrov.com/wiki/runtime-narrative/tutorial.html" },
      { id: "quickstart", title: "Quick Start", href: "https://mogrov.com/wiki/runtime-narrative/quickstart.html" },
      { id: "concepts", title: "Core Concepts", href: "https://mogrov.com/wiki/runtime-narrative/concepts.html" },
    ],
  },
  {
    group: "Core API",
    items: [
      { id: "story", title: "story()", href: "https://mogrov.com/wiki/runtime-narrative/story.html" },
      { id: "stage", title: "stage()", href: "https://mogrov.com/wiki/runtime-narrative/stage.html" },
      { id: "decorators", title: "Decorators", href: "https://mogrov.com/wiki/runtime-narrative/decorators.html" },
      { id: "auto-instrumentation", title: "Auto-Instrumentation", href: "https://mogrov.com/wiki/runtime-narrative/auto-instrumentation.html" },
    ],
  },
  {
    group: "Diagnostics & Analysis",
    items: [
      { id: "diagnostics", title: "Failure Diagnostics", href: "https://mogrov.com/wiki/runtime-narrative/diagnostics.html" },
      { id: "custom-analyzers", title: "Custom Failure Analyzers", href: "https://mogrov.com/wiki/runtime-narrative/custom-analyzers.html" },
      { id: "background-analysis", title: "Background Analysis", href: "https://mogrov.com/wiki/runtime-narrative/background-analysis.html" },
    ],
  },
  {
    group: "Renderers",
    items: [
      { id: "renderers", title: "Renderers", href: "https://mogrov.com/wiki/runtime-narrative/renderers.html" },
      { id: "custom-renderers", title: "Custom Renderers", href: "https://mogrov.com/wiki/runtime-narrative/custom-renderers.html" },
    ],
  },
  {
    group: "Integrations & Concurrency",
    items: [
      { id: "integrations", title: "Framework Integrations", href: "https://mogrov.com/wiki/runtime-narrative/integrations.html" },
      { id: "task-groups", title: "Async Task Groups", href: "https://mogrov.com/wiki/runtime-narrative/task-groups.html" },
      { id: "substories-logging", title: "Sub-stories & Log Capture", href: "https://mogrov.com/wiki/runtime-narrative/substories-logging.html" },
    ],
  },
  {
    group: "Operations",
    items: [
      { id: "persistence-cli", title: "SQLite Persistence & CLI", href: "https://mogrov.com/wiki/runtime-narrative/persistence-cli.html" },
      { id: "testing", title: "Testing with StoryRecorder", href: "https://mogrov.com/wiki/runtime-narrative/testing.html" },
      { id: "dry-run", title: "dry_run Mode", href: "https://mogrov.com/wiki/runtime-narrative/dry-run.html" },
      { id: "env-vars", title: "Environment Variables", href: "https://mogrov.com/wiki/runtime-narrative/env-vars.html" },
    ],
  },
  {
    group: "Reference",
    items: [
      { id: "events", title: "Event Reference", href: "https://mogrov.com/wiki/runtime-narrative/events.html" },
      { id: "examples", title: "Examples", href: "https://mogrov.com/wiki/runtime-narrative/examples.html" },
    ],
  },
];
