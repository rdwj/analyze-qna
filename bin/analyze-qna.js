#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function run(cmd, args, options = {}) {
  const result = spawnSync(cmd, args, {
    stdio: 'inherit',
    ...options,
  });
  if (result.error) {
    console.error(`[analyze-qna] Failed to run: ${cmd} ${args.join(' ')}`);
    console.error(result.error);
    process.exit(result.status || 1);
  }
  if (result.status !== 0) {
    process.exit(result.status);
  }
}

function findPython() {
  let result = spawnSync('python3', ['--version'], { stdio: 'ignore' });
  if (result && result.status === 0) return 'python3';
  result = spawnSync('python', ['--version'], { stdio: 'ignore' });
  if (result && result.status === 0) return 'python';
  console.error('[analyze-qna] Python is required but was not found. Install Python 3.');
  process.exit(1);
}

(function main() {
  const rootDir = path.resolve(__dirname, '..');
  const venvDir = path.join(rootDir, '.venv');
  const python = findPython();

  if (!fs.existsSync(venvDir)) {
    run(python, ['-m', 'venv', venvDir]);
  }

  const venvBin = path.join(venvDir, process.platform === 'win32' ? 'Scripts' : 'bin');
  const venvPython = path.join(venvBin, process.platform === 'win32' ? 'python.exe' : 'python');
  const env = {
    ...process.env,
    VIRTUAL_ENV: venvDir,
    PATH: `${venvBin}${path.delimiter}${process.env.PATH}`,
  };

  // Install requirements
  run(venvPython, ['-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade', 'pip'], { env });
  run(venvPython, ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', path.join(rootDir, 'requirements.txt')], { env });

  // Forward args to Python CLI
  const args = process.argv.slice(2);
  const scriptPath = path.join(rootDir, 'src', 'analyze_qna.py');
  run(venvPython, [scriptPath, ...args], { env });
})();
