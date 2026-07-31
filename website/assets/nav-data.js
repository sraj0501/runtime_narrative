/* Single source of truth for site navigation.
   `id` must match the `data-page` attribute on each page's <body>.
   `href` is always root-relative (starts with "/"). */
window.NARRATIVE_NAV = [
  {
    group: "Showcase",
    items: [
      { id: "showcase", title: "See It In Action", href: "/docs/showcase.html" },
    ],
  },
  {
    group: "Getting Started",
    items: [
      { id: "installation", title: "Installation", href: "/docs/installation.html" },
      { id: "tutorial", title: "Tutorial: Your First Story", href: "/docs/tutorial.html" },
      { id: "quickstart", title: "Quick Start", href: "/docs/quickstart.html" },
      { id: "concepts", title: "Core Concepts", href: "/docs/concepts.html" },
    ],
  },
  {
    group: "Core API",
    items: [
      { id: "story", title: "story()", href: "/docs/story.html" },
      { id: "stage", title: "stage()", href: "/docs/stage.html" },
      { id: "decorators", title: "Decorators", href: "/docs/decorators.html" },
      { id: "auto-instrumentation", title: "Auto-Instrumentation", href: "/docs/auto-instrumentation.html" },
    ],
  },
  {
    group: "Diagnostics & Analysis",
    items: [
      { id: "diagnostics", title: "Failure Diagnostics", href: "/docs/diagnostics.html" },
      { id: "custom-analyzers", title: "Custom Failure Analyzers", href: "/docs/custom-analyzers.html" },
      { id: "background-analysis", title: "Background Analysis", href: "/docs/background-analysis.html" },
    ],
  },
  {
    group: "Renderers",
    items: [
      { id: "renderers", title: "Renderers", href: "/docs/renderers.html" },
      { id: "custom-renderers", title: "Custom Renderers", href: "/docs/custom-renderers.html" },
    ],
  },
  {
    group: "Integrations & Concurrency",
    items: [
      { id: "integrations", title: "Framework Integrations", href: "/docs/integrations.html" },
      { id: "task-groups", title: "Async Task Groups", href: "/docs/task-groups.html" },
      { id: "substories-logging", title: "Sub-stories & Log Capture", href: "/docs/substories-logging.html" },
    ],
  },
  {
    group: "Operations",
    items: [
      { id: "persistence-cli", title: "SQLite Persistence & CLI", href: "/docs/persistence-cli.html" },
      { id: "testing", title: "Testing with StoryRecorder", href: "/docs/testing.html" },
      { id: "dry-run", title: "dry_run Mode", href: "/docs/dry-run.html" },
      { id: "env-vars", title: "Environment Variables", href: "/docs/env-vars.html" },
    ],
  },
  {
    group: "Reference",
    items: [
      { id: "events", title: "Event Reference", href: "/docs/events.html" },
      { id: "examples", title: "Examples", href: "/docs/examples.html" },
    ],
  },
];
