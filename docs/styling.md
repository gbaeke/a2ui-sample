# Styling: who decides how a surface looks

Written on 2026-11-13. The question: in basic-catalog mode, can the agent be told to use the
client's design scheme, such as its colours and fonts?

Short answer: no, and it does not need to be. In A2UI 1.0 the agent says what to show and the
client decides how it looks. Styling is set on the client, not in the prompt.

The CSS variables below were read from the installed `@a2ui/web_core` 0.15.0. Overriding them has
not been tried in this sample.

## The protocol has no styling channel

- Version 0.9 had a `theme` property on `createSurface` and in the catalog, with `primaryColor`.
  Version 1.0 removed both, to separate layout from branding. The protocol document calls this
  "decoupled branding": visual styling is left to the target framework's own theme.
- A 1.0 `createSurface` that carries `theme` is invalid.
- The basic components (`Card`, `Column`, `Row`, `Text`, `Divider`, `Button` and the rest) have no
  colour or font properties.

So a prompt instruction such as "use our brand blue" has nothing to act on. The model cannot
express it in a valid message.

## The client themes the basic catalog

Each renderer draws the basic components in its own style:

| Client | How it is themed |
| --- | --- |
| Web (`@a2ui/react`, also Lit and Angular) | CSS variables |
| Flutter, SwiftUI, Jetpack Compose | The framework's native theme |
| The text client in `cli/` | Its own ANSI colours |

The same agent output therefore looks like each client's own product.

### The web renderer's variables

The defaults are declared on `:where(:root)`, which has no specificity, so a plain `:root` rule in
the app's own CSS overrides them. The main ones:

| Group | Variables |
| --- | --- |
| Colours | `--a2ui-color-primary`, `--a2ui-color-on-primary`, `--a2ui-color-secondary`, `--a2ui-color-background`, `--a2ui-color-surface`, `--a2ui-color-on-surface`, `--a2ui-color-border`, `--a2ui-color-input` |
| Fonts | `--default-font-family`, `--a2ui-font-family-title`, `--a2ui-font-scale`, `--a2ui-font-size-xs` to `--a2ui-font-size-2xl` |
| Spacing and shape | `--a2ui-spacing-xs` to `--a2ui-spacing-xl`, `--a2ui-border-radius`, `--a2ui-border-width` |
| Per component | `--a2ui-button-border-radius`, `--a2ui-card-border-radius`, `--a2ui-textfield-border-radius` and similar |

An override in `web/src/styles.css` would look like this:

```css
:root {
  --a2ui-color-primary: #0b6e4f;
  --a2ui-card-border-radius: 12px;
  --default-font-family: 'Inter', sans-serif;
}
```

The default theme follows the user's light or dark preference (`color-scheme: light dark`). The
classes `a2ui-light` and `a2ui-dark` force one of the two.

This sample sets none of these variables, which is why the basic-mode screens look plain.

## What the agent can still steer

Structure, not appearance:

- which components it uses, and their order and grouping;
- the `Text` variant (`body` or `caption` in 1.0);
- what goes in a `Card`, a `Row` or a `Column`.

The `UI_BASIC` conventions in `agent/hours_agent/llm.py` do this for basic mode.

## Brand-specific choices need a custom catalog

If the agent should be able to choose between looks that carry meaning, such as a warning tone or
a highlighted card, define a component for it in a custom catalog. The client implements the
component and its look, and the agent only picks it and sets its properties.

`StatusPill` in `catalog/hours_catalog.json` is an example: the agent sets `tone` to `ok`,
`warning` or `over`, and each client decides which colour that is.

## Sources

- A2UI 1.0 protocol document, "Decoupled Branding", and the 1.0 evolution guide, in the
  `a2ui-project/a2ui` repository under `specification/v1_0/docs/`.
- Default theme of the web renderers: `@a2ui/web_core`,
  `src/universal/basic_catalog/styles/default.js`.
