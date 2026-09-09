import {createHash} from 'node:crypto';
import {constants, createReadStream} from 'node:fs';
import {copyFile, lstat, mkdir, mkdtemp, realpath, rm, unlink, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {MakerSquirrel} from '@electron-forge/maker-squirrel';
import type {MakerOptions} from '@electron-forge/maker-base';

function samePath(left: string, right: string) {
  return process.platform === 'win32' ? left.toLowerCase() === right.toLowerCase() : left === right;
}

function absoluteAsciiRoot(value: string, error: string) {
  if (!path.isAbsolute(value) || !/^[\x20-\x7e]+$/.test(value) || value.split(/[\\/]/).includes('..')) {
    throw new Error(error);
  }
  return path.resolve(value);
}

async function safeDirectory(directory: string, allowMissing = false) {
  let current = path.resolve(directory);
  for (;;) {
    try {
      const stat = await lstat(current);
      if (!stat.isDirectory() || stat.isSymbolicLink() || !samePath(await realpath(current), current)) {
        throw new Error('SQUIRREL_UNSAFE_PATH');
      }
    } catch (error) {
      if (!allowMissing || (error as NodeJS.ErrnoException).code !== 'ENOENT') {
        throw new Error('SQUIRREL_UNSAFE_PATH', {cause: error});
      }
    }
    const parent = path.dirname(current);
    if (parent === current) return;
    current = parent;
  }
}

async function safeFile(file: string, allowMissing = false) {
  await safeDirectory(path.dirname(file), allowMissing);
  try {
    const stat = await lstat(file);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1 || !samePath(await realpath(file), path.resolve(file))) {
      throw new Error('SQUIRREL_INVALID_ARTIFACT');
    }
    return true;
  } catch (error) {
    if (!allowMissing || (error as NodeJS.ErrnoException).code !== 'ENOENT') {
      throw new Error('SQUIRREL_INVALID_ARTIFACT', {cause: error});
    }
    return false;
  }
}

function artifactRelativeTo(directory: string, artifact: string) {
  if (!path.isAbsolute(artifact) || artifact.split(/[\\/]/).includes('..')) throw new Error('SQUIRREL_INVALID_ARTIFACT');
  const relative = path.relative(directory, artifact);
  if (!relative || relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) {
    throw new Error('SQUIRREL_INVALID_ARTIFACT');
  }
  return relative;
}

type ArtifactCopy = {source: string; destination: string};
type OriginalArtifact = ArtifactCopy & {backup: string | null; originalSha256: string | null};

async function fileDigest(file: string) {
  const digest = createHash('sha256');
  for await (const chunk of createReadStream(file)) digest.update(chunk);
  return digest.digest('hex');
}

class ArtifactRollbackError extends Error {
  constructor(readonly recoveryDirectory: string, failures: unknown[]) {
    super(`SQUIRREL_COPY_ROLLBACK_FAILED: recovery retained at ${recoveryDirectory}`, {cause: new AggregateError(failures)});
  }
}

async function publishArtifacts(copies: ArtifactCopy[], recoveryDirectory: string) {
  await safeDirectory(path.dirname(recoveryDirectory));
  await mkdir(recoveryDirectory);
  const originals: OriginalArtifact[] = [];
  // Capture all prior files before the first write. The manifest is sufficient to identify every recovery copy.
  for (const [index, copy] of copies.entries()) {
    const original: OriginalArtifact = {...copy, backup: null, originalSha256: null};
    if (await safeFile(copy.destination, true)) {
      original.backup = `original-${index}`;
      original.originalSha256 = await fileDigest(copy.destination);
      const backup = path.join(recoveryDirectory, original.backup);
      await copyFile(copy.destination, backup, constants.COPYFILE_EXCL);
      await safeFile(backup);
      if (await fileDigest(backup) !== original.originalSha256) throw new Error('SQUIRREL_BACKUP_MISMATCH');
    }
    originals.push(original);
  }
  await writeFile(path.join(recoveryDirectory, 'manifest.json'), JSON.stringify({schemaVersion: 1,
    artifacts: originals.map(({destination, backup, originalSha256}) => ({destination, backup, originalSha256}))}, null, 2) + '\n', {flag: 'wx'});
  const attempted: OriginalArtifact[] = [];
  try {
    for (const original of originals) {
      await mkdir(path.dirname(original.destination), {recursive: true});
      await safeFile(original.destination, true);
      // Include a failed copy: a filesystem error may occur after truncating or partially writing the target.
      attempted.push(original);
      await copyFile(original.source, original.destination);
    }
  } catch (error) {
    const rollbackFailures: unknown[] = [];
    for (const original of attempted.reverse()) {
      try {
        const exists = await safeFile(original.destination, true);
        if (original.backup) {
          // A failed write to a read-only file may leave it untouched; do not change its attributes or rewrite it.
          if (exists && await fileDigest(original.destination) === original.originalSha256) continue;
          const backup = path.join(recoveryDirectory, original.backup);
          await safeFile(backup);
          if (await fileDigest(backup) !== original.originalSha256) throw new Error('SQUIRREL_BACKUP_MISMATCH');
          await copyFile(backup, original.destination);
          if (await fileDigest(original.destination) !== original.originalSha256) throw new Error('SQUIRREL_ROLLBACK_MISMATCH');
        } else if (exists) {
          // Only remove a file this run attempted to create; never recursively delete the output directory.
          await unlink(original.destination);
        }
      } catch (rollbackError) {
        rollbackFailures.push(rollbackError);
      }
    }
    if (rollbackFailures.length) throw new ArtifactRollbackError(recoveryDirectory, [error, ...rollbackFailures]);
    throw error;
  }
}

/** Keep rcedit's EXE output paths ASCII without changing the product or Forge's final output paths. */
export class AsciiStagingSquirrelMaker extends MakerSquirrel {
  override async make(options: MakerOptions): Promise<string[]> {
    // The original maker also copies Squirrel.exe into os.tmpdir() before resource editing.
    // An explicit output staging root cannot make a non-ASCII system TEMP work.
    const systemTemp = absoluteAsciiRoot(os.tmpdir(), 'SQUIRREL_ASCII_SYSTEM_TEMP_REQUIRED');
    await safeDirectory(systemTemp);
    // Optional existing ASCII directory; read per make so Forge's inherited clone keeps its normal contract.
    const stagingRoot = absoluteAsciiRoot(process.env.YIKE_SQUIRREL_STAGING_ROOT ?? systemTemp, 'SQUIRREL_INVALID_STAGING_ROOT');
    await safeDirectory(stagingRoot);
    if (!/^[a-zA-Z0-9_-]+$/.test(options.targetArch)) throw new Error('SQUIRREL_INVALID_ARCH');
    if (!path.isAbsolute(options.makeDir)) throw new Error('SQUIRREL_UNSAFE_PATH');
    const destinationDirectory = path.join(options.makeDir, 'squirrel.windows', options.targetArch);
    await safeDirectory(destinationDirectory, true);

    const staging = await mkdtemp(path.join(stagingRoot, 'yike-squirrel-'));
    const identity = await lstat(staging);
    let preserveRecovery = false;
    try {
      // MakerSquirrel.ensureDirectory is destructive, so it must only receive our new private run directory.
      const artifacts = await super.make({...options, makeDir: staging});
      if (!artifacts.length) throw new Error('SQUIRREL_INVALID_ARTIFACT');
      const stagedOutput = path.join(staging, 'squirrel.windows', options.targetArch);
      const seen = new Set<string>();
      const copies: ArtifactCopy[] = [];
      // Validate the entire result before copying anything into the user's output directory.
      for (const artifact of artifacts) {
        const relative = artifactRelativeTo(stagedOutput, artifact);
        const key = process.platform === 'win32' ? relative.toLowerCase() : relative;
        if (seen.has(key)) throw new Error('SQUIRREL_INVALID_ARTIFACT');
        seen.add(key);
        await safeFile(artifact);
        const destination = path.join(destinationDirectory, relative);
        await safeFile(destination, true);
        copies.push({source: artifact, destination});
      }
      await publishArtifacts(copies, path.join(staging, 'recovery'));
      return copies.map(value => value.destination);
    } catch (error) {
      preserveRecovery = error instanceof ArtifactRollbackError;
      throw error;
    } finally {
      // An incomplete rollback leaves the only prior copies here. Keep them and the manifest for recovery.
      if (!preserveRecovery) {
        // Never recursively remove the original makeDir, a sibling run, or a replaced/redirected staging root.
        if (!samePath(path.dirname(staging), stagingRoot) || !path.basename(staging).startsWith('yike-squirrel-')) {
          throw new Error('SQUIRREL_UNSAFE_STAGING_CLEANUP');
        }
        await safeDirectory(staging);
        const current = await lstat(staging);
        if (current.dev !== identity.dev || current.ino !== identity.ino) throw new Error('SQUIRREL_UNSAFE_STAGING_CLEANUP');
        // fs.rm removes contained symlinks/junctions themselves; it does not traverse their targets.
        await rm(staging, {recursive: true});
      }
    }
  }
}
