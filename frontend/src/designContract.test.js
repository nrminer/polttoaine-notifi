const fs = require("fs");
const path = require("path");

const frontendRoot = path.resolve(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(frontendRoot, relativePath), "utf8");
}

test("ASEMATAULU implementation removes generic AI dashboard markers", () => {
  const implementation = [
    "public/index.html",
    "src/index.css",
    "src/App.css",
    "src/App.js",
    "src/components/Card.jsx",
    "tailwind.config.js",
  ]
    .map(read)
    .join("\n");

  expect(implementation).not.toMatch(/Inter/);
  expect(implementation).not.toMatch(/#2563EB/i);
  expect(implementation).not.toMatch(/glass-panel/);
  expect(implementation).not.toMatch(/Aether Fuel Dashboard/);
});
