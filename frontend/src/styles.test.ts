import { readFileSync } from "node:fs";
import path from "node:path";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import { describe, expect, it } from "vitest";

// `npm test` runs from the frontend package root, which is also where the
// Tailwind config's relative `content` globs resolve from.
const frontendRoot = process.cwd();

async function compileStyles() {
  const source = readFileSync(path.join(frontendRoot, "src/index.css"), "utf8");

  return postcss([
    tailwindcss({
      config: path.join(frontendRoot, "tailwind.config.js"),
    }),
  ]).process(source, {
    from: path.join(frontendRoot, "src/index.css"),
  });
}

describe("Tailwind theme", () => {
  it("compiles the stylesheet and emits custom opacity utilities", async () => {
    const result = await compileStyles();

    expect(result.warnings()).toHaveLength(0);
    expect(result.css).toContain(".bg-berry\\/10");
    expect(result.css).toContain(".bg-berry\\/15");
    // The regression that broke the app: `bg-berry/70` inside @apply used to
    // fail because the custom color had no alpha channel support. Reaching
    // this assertion means PostCSS/Tailwind compiled the stylesheet.
    expect(result.css).toContain(
      "background-color: rgb(var(--color-berry-rgb) / 0.7);",
    );
    expect(result.css).toContain("--color-berry-rgb: 168 61 131;");
    expect(result.css).toContain("border-color: rgb(var(--color-lavender-rgb) /");
  });

  it("keeps palette channels in sync with the hex variables", async () => {
    const source = readFileSync(path.join(frontendRoot, "src/index.css"), "utf8");

    expect(source).toContain("--color-berry-rgb: 168 61 131;");
    expect(source).toContain("--berry-pink: #a83d83;");
    expect(source).toContain("--color-neon-rgb: 233 79 168;");
    expect(source).toContain("--color-lavender-rgb: 183 139 255;");
  });
});
