import {execFileSync} from 'node:child_process';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {dirname, parse, resolve} from 'node:path';

const ALLOWED_CODECS = new Set(['h264', 'h265', 'vp8', 'vp9']);
const ALLOWED_CHROME_MODES = new Set(['headless-shell', 'chrome-for-testing']);

export function validateCodec(codec) {
  if (!ALLOWED_CODECS.has(codec)) {
    throw new Error(`Unsupported codec: ${codec}`);
  }
  return codec;
}

export function validateChromeMode(chromeMode) {
  if (!ALLOWED_CHROME_MODES.has(chromeMode)) {
    throw new Error(`Unsupported chrome mode: ${chromeMode}`);
  }
  return chromeMode;
}

export function getAudioDuration(
  filePath,
  {
    executor = execFileSync,
    ffprobeExecutable = 'ffprobe',
    ffprobePrefixArgs = [],
  } = {},
) {
  try {
    const result = executor(
      ffprobeExecutable,
      [
        ...ffprobePrefixArgs,
        '-v',
        'error',
        '-show_entries',
        'format=duration',
        '-of',
        'csv=p=0',
        String(filePath),
      ],
      {
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: false,
      },
    ).trim();
    const duration = Number.parseFloat(result);
    return Number.isFinite(duration) && duration > 0 ? duration : null;
  } catch {
    return null;
  }
}

function findPackageJsonFromEntry(entryPath, readFile = readFileSync) {
  let current = dirname(entryPath);
  const root = parse(current).root;
  while (true) {
    const candidate = resolve(current, 'package.json');
    if (existsSync(candidate)) {
      try {
        const payload = JSON.parse(readFile(candidate, 'utf-8'));
        if (payload.name === '@remotion/cli') {
          return candidate;
        }
      } catch {
        // Continue toward the filesystem root and report one useful error below.
      }
    }
    if (current === root) break;
    current = dirname(current);
  }
  throw new Error('Could not locate @remotion/cli package.json');
}

export function resolveRemotionCliPath(
  {
    requireFn = createRequire(import.meta.url),
    readFile = readFileSync,
    packageJsonPath = null,
  } = {},
) {
  let resolvedPackageJson = packageJsonPath;
  if (!resolvedPackageJson) {
    try {
      resolvedPackageJson = requireFn.resolve('@remotion/cli/package.json');
    } catch {
      const entryPath = requireFn.resolve('@remotion/cli');
      resolvedPackageJson = findPackageJsonFromEntry(entryPath, readFile);
    }
  }

  const packageJson = JSON.parse(readFile(resolvedPackageJson, 'utf-8'));
  const bin = typeof packageJson.bin === 'string'
    ? packageJson.bin
    : packageJson.bin?.remotion;
  if (!bin || typeof bin !== 'string') {
    throw new Error('@remotion/cli does not declare the remotion executable');
  }

  const cliPath = resolve(dirname(resolvedPackageJson), bin);
  if (!existsSync(cliPath)) {
    throw new Error(`Remotion CLI entry point not found: ${cliPath}`);
  }
  return cliPath;
}

export function buildRemotionArgs({
  output,
  propsFile,
  codec,
  browserExe = null,
  chromeMode = 'headless-shell',
}) {
  validateCodec(codec);
  validateChromeMode(chromeMode);

  const args = [
    'render',
    'MusicVideo',
    String(output),
    `--props=${propsFile}`,
    `--codec=${codec}`,
    '--log=error',
  ];
  if (browserExe) {
    args.push(`--browser-executable=${browserExe}`);
  }
  if (chromeMode !== 'headless-shell') {
    args.push(`--chrome-mode=${chromeMode}`);
  }
  return args;
}

export function runRemotionRender(
  options,
  {
    executor = execFileSync,
    nodeExecutable = process.execPath,
    remotionCliPath = null,
  } = {},
) {
  const cliPath = remotionCliPath ?? resolveRemotionCliPath();
  const args = [cliPath, ...buildRemotionArgs(options)];
  return executor(nodeExecutable, args, {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  });
}
