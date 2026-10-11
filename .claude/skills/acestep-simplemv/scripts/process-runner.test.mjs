import assert from 'node:assert/strict';
import {chmodSync, existsSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import test from 'node:test';

import {
  buildRemotionArgs,
  getAudioDuration,
  resolveRemotionCliPath,
  runRemotionRender,
  validateCodec,
  validateChromeMode,
} from './process-runner.mjs';

test('ffprobe receives a metacharacter filename as one opaque argv element', () => {
  let observed;
  const duration = getAudioDuration('song$(touch SHOULD_NOT_EXIST);x.mp3', {
    executor(executable, args, options) {
      observed = {executable, args, options};
      return '12.375\n';
    },
  });
  assert.equal(duration, 12.375);
  assert.equal(observed.executable, 'ffprobe');
  assert.equal(observed.args.at(-1), 'song$(touch SHOULD_NOT_EXIST);x.mp3');
  assert.equal(observed.options.shell, false);
});

test('actual ffprobe execution keeps a metacharacter media path opaque', () => {
  const directory = mkdtempSync(join(tmpdir(), 'simplemv-ffprobe-no-shell-'));
  const marker = join(directory, 'marker-created');
  const stub = join(directory, 'fake-ffprobe.mjs');
  writeFileSync(stub, "process.stdout.write('9.75\\n');\n", 'utf-8');
  const mediaPath = join(directory, `song$(touch ${marker}).mp3`);
  const duration = getAudioDuration(mediaPath, {
    ffprobeExecutable: process.execPath,
    ffprobePrefixArgs: [stub],
  });
  assert.equal(duration, 9.75);
  assert.equal(existsSync(marker), false);
});

test('actual execFile path preserves command substitutions literally', () => {
  const directory = mkdtempSync(join(tmpdir(), 'simplemv-no-shell-'));
  const marker = join(directory, 'marker-created');
  const capture = join(directory, 'captured.json');
  const cli = join(directory, 'fake-remotion-cli.mjs');
  writeFileSync(
    cli,
    `import {writeFileSync} from 'node:fs';\nwriteFileSync(${JSON.stringify(capture)}, JSON.stringify(process.argv.slice(2)));\n`,
    'utf-8',
  );
  chmodSync(cli, 0o755);
  const maliciousOutput = join(directory, `video$(touch ${marker}).mp4`);
  const result = runRemotionRender(
    {
      output: maliciousOutput,
      propsFile: join(directory, 'props;echo-not-run.json'),
      codec: 'h264',
      browserExe: join(directory, 'browser$(touch not-run)'),
      chromeMode: 'chrome-for-testing',
    },
    {remotionCliPath: cli},
  );
  assert.equal(result, '');
  assert.equal(existsSync(marker), false);
  const captured = JSON.parse(readFileSync(capture, 'utf-8'));
  assert.equal(captured[0], 'render');
  assert.equal(captured[1], 'MusicVideo');
  assert.equal(captured[2], maliciousOutput);
  assert.match(captured[3], /^--props=/);
  assert.match(captured[6], /^--browser-executable=/);
});

test('codec and chrome mode are strict allowlists', () => {
  for (const codec of ['h264', 'h265', 'vp8', 'vp9']) {
    assert.equal(validateCodec(codec), codec);
  }
  assert.throws(() => validateCodec('h264;touch marker'), /Unsupported codec/);
  assert.equal(validateChromeMode('headless-shell'), 'headless-shell');
  assert.equal(validateChromeMode('chrome-for-testing'), 'chrome-for-testing');
  assert.throws(() => validateChromeMode('chrome;touch marker'), /Unsupported chrome mode/);
});

test('render argv preserves normal options without shell reconstruction', () => {
  assert.deepEqual(
    buildRemotionArgs({
      output: 'out/video.mp4',
      propsFile: '/tmp/props.json',
      codec: 'vp9',
      browserExe: '/opt/Browser With Space/chrome',
      chromeMode: 'chrome-for-testing',
    }),
    [
      'render',
      'MusicVideo',
      'out/video.mp4',
      '--props=/tmp/props.json',
      '--codec=vp9',
      '--log=error',
      '--browser-executable=/opt/Browser With Space/chrome',
      '--chrome-mode=chrome-for-testing',
    ],
  );
});

test('remotion CLI path is derived from its declared package bin', () => {
  const directory = mkdtempSync(join(tmpdir(), 'simplemv-package-'));
  const cli = join(directory, 'remotion-cli.js');
  const packageJson = join(directory, 'package.json');
  writeFileSync(cli, '// inert fixture\n', 'utf-8');
  writeFileSync(
    packageJson,
    JSON.stringify({name: '@remotion/cli', bin: {remotion: 'remotion-cli.js'}}),
    'utf-8',
  );
  assert.equal(resolveRemotionCliPath({packageJsonPath: packageJson}), cli);
});

test('invalid choices fail before an executor is called', () => {
  let called = false;
  assert.throws(
    () => runRemotionRender(
      {
        output: 'out.mp4',
        propsFile: 'props.json',
        codec: 'h264 && malicious',
        chromeMode: 'headless-shell',
      },
      {
        remotionCliPath: '/tmp/fake-cli',
        executor() {
          called = true;
          return '';
        },
      },
    ),
    /Unsupported codec/,
  );
  assert.equal(called, false);
});
