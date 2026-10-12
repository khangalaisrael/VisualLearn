/**
 * Builds the Chrome Web Store package: `npm run package:store`.
 *
 * Same inputs as scripts/make-friends-zip.ps1 (the shared API key is read from
 * a file outside the repository and never printed), plus what the store needs:
 * no "key" in the manifest, and the store item's own Google sign-in client.
 * Runs on Windows, macOS and Linux with nothing but Node.
 *
 * Options (command line or environment):
 *   --key-file <path>   VISIONLEARN_KEY_FILE   default ~/.visionlearn_key
 *   --backend <url>     VITE_BACKEND_URL       default https://visionlearn.fyi
 *   --client-id <id>    STORE_OAUTH_CLIENT_ID  Google sign-in client for the store ID
 *   --out <path>        VISIONLEARN_STORE_ZIP  default visionlearn-chrome-web-store-<version>.zip
 *
 * The zip holds the shared key, so it must never be committed (*.zip is ignored).
 * See docs/CHROME_WEB_STORE.md.
 */

import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { deflateRawSync } from "node:zlib";

const extensionDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function option(flag, envName, fallback) {
  const index = process.argv.indexOf(flag);
  if (index !== -1 && process.argv[index + 1]) return process.argv[index + 1];
  return process.env[envName] || fallback;
}

function fail(message) {
  console.error(`\n✗ ${message}\n`);
  process.exit(1);
}

const keyFile = option("--key-file", "VISIONLEARN_KEY_FILE", join(homedir(), ".visionlearn_key"));
const backend = option("--backend", "VITE_BACKEND_URL", "https://visionlearn.fyi").replace(/\/+$/, "");
const clientId = option("--client-id", "STORE_OAUTH_CLIENT_ID", "");
const version = JSON.parse(readFileSync(join(extensionDir, "manifest.json"), "utf8")).version;
const out = resolve(option("--out", "VISIONLEARN_STORE_ZIP", join(extensionDir, `visionlearn-chrome-web-store-${version}.zip`)));

if (!existsSync(keyFile)) fail(`Key file not found: ${keyFile}\n  Put the server's LOCAL_API_KEY in it, or pass --key-file <path>.`);
const apiKey = readFileSync(keyFile, "utf8").trim();
if (!apiKey) fail(`Key file is empty: ${keyFile}`);
if (!backend.startsWith("https://")) fail(`The backend address must start with https:// (got ${backend}).`);

const stage = mkdtempSync(join(tmpdir(), "visionlearn-store-"));
try {
  console.log(`Building version ${version} for ${backend}…`);
  const viteBin = join(extensionDir, "node_modules", "vite", "bin", "vite.js");
  if (!existsSync(viteBin)) fail("Vite is not installed. Run `npm install` in extension/ first.");
  const build = spawnSync(process.execPath, [viteBin, "build", "--outDir", stage, "--emptyOutDir"], {
    cwd: extensionDir,
    stdio: ["ignore", "ignore", "inherit"],
    env: {
      ...process.env,
      STORE_BUILD: "1",
      VITE_BACKEND_URL: backend,
      VITE_LOCAL_API_KEY: apiKey,
      STORE_OAUTH_CLIENT_ID: clientId,
    },
  });
  if (build.status !== 0) fail("The build failed (see the errors above).");

  // Checks that would otherwise only surface as a rejected upload or a broken install.
  const manifest = JSON.parse(readFileSync(join(stage, "manifest.json"), "utf8"));
  if ("key" in manifest) fail('The built manifest still has a "key"; the store would refuse it.');
  const files = listFiles(stage);
  const bundle = files.filter((file) => file.endsWith(".js")).map((file) => readFileSync(file, "utf8")).join("\n");
  if (!bundle.includes(backend)) fail(`The build does not contain the backend address ${backend}.`);
  if (!bundle.includes(apiKey)) fail("The build does not contain the API key.");

  writeZip(
    out,
    files.map((file) => ({ name: relative(stage, file).split(sep).join("/"), data: readFileSync(file) }))
  );
  const megabytes = (statSync(out).size / 1024 / 1024).toFixed(2);
  console.log(`\n✓ Created ${out} (${megabytes} MB, ${files.length} files).`);
  if (clientId) {
    console.log(`  Google sign-in client: ${manifest.oauth2.client_id}`);
  } else {
    console.log(
      "  ! No --client-id given: Google sign-in will not work in the store version until you rebuild\n" +
        "    with the store item's own OAuth client (docs/CHROME_WEB_STORE.md, step 5). Uploading\n" +
        "    this zip as a draft to learn the item's ID is fine."
    );
  }
  console.log("  Upload it in the Chrome Web Store developer dashboard. Do not commit this file.");
} finally {
  rmSync(stage, { recursive: true, force: true });
}

function listFiles(dir) {
  return readdirSync(dir, { withFileTypes: true })
    .flatMap((entry) => (entry.isDirectory() ? listFiles(join(dir, entry.name)) : [join(dir, entry.name)]))
    .sort();
}

// A minimal zip writer (deflate, forward-slash paths), so packaging needs no
// extra dependency or platform zip tool.
function writeZip(path, entries) {
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc32 = (data) => {
    let crc = 0xffffffff;
    for (const byte of data) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  };

  const local = [];
  const central = [];
  let offset = 0;
  for (const { name, data } of entries) {
    const nameBytes = Buffer.from(name, "utf8");
    const compressed = deflateRawSync(data, { level: 9 });
    const crc = crc32(data);
    // DOS date 2026-01-01 00:00, fixed so the same build gives the same zip.
    const time = 0;
    const date = ((2026 - 1980) << 9) | (1 << 5) | 1;

    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50, 0);
    header.writeUInt16LE(20, 4); // version needed
    header.writeUInt16LE(0x0800, 6); // UTF-8 names
    header.writeUInt16LE(8, 8); // deflate
    header.writeUInt16LE(time, 10);
    header.writeUInt16LE(date, 12);
    header.writeUInt32LE(crc, 14);
    header.writeUInt32LE(compressed.length, 18);
    header.writeUInt32LE(data.length, 22);
    header.writeUInt16LE(nameBytes.length, 26);
    header.writeUInt16LE(0, 28);
    local.push(header, nameBytes, compressed);

    const record = Buffer.alloc(46);
    record.writeUInt32LE(0x02014b50, 0);
    record.writeUInt16LE(20, 4); // version made by
    record.writeUInt16LE(20, 6); // version needed
    record.writeUInt16LE(0x0800, 8);
    record.writeUInt16LE(8, 10);
    record.writeUInt16LE(time, 12);
    record.writeUInt16LE(date, 14);
    record.writeUInt32LE(crc, 16);
    record.writeUInt32LE(compressed.length, 20);
    record.writeUInt32LE(data.length, 24);
    record.writeUInt16LE(nameBytes.length, 28);
    record.writeUInt32LE(offset, 42);
    central.push(record, nameBytes);

    offset += header.length + nameBytes.length + compressed.length;
  }

  const centralSize = central.reduce((sum, part) => sum + part.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(offset, 16);
  writeFileSync(path, Buffer.concat([...local, ...central, end]));
}
