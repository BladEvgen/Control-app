import { ComponentType, lazy, LazyExoticComponent } from "react";
import {
  isAbortLikeLoadError,
  isChunkLoadError,
  tryRecoverChunkLoadError,
} from "./chunkRecovery";

const ABORT_RETRY_LIMIT = 2;
const ABORT_RETRY_DELAY_MS = 180;
const CHUNK_RETRY_LIMIT = 2;
const CHUNK_RETRY_DELAY_MS = 260;

const sleep = (ms: number) =>
  new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });

type ImportedComponent<TModule> = TModule extends { default: infer TComponent }
  ? TComponent extends ComponentType<infer Props>
    ? ComponentType<Props> & TComponent
    : never
  : never;

export const lazyWithRetry = <TModule extends { default: unknown }>(
  importer: () => Promise<TModule>,
): LazyExoticComponent<ImportedComponent<TModule>> => {
  return lazy<ImportedComponent<TModule>>(async () => {
    const importWithRetry = async (
      attempt = 0,
    ): Promise<{ default: ImportedComponent<TModule> }> => {
      try {
        const module = await importer();
        return module as { default: ImportedComponent<TModule> };
      } catch (error) {
        if (isAbortLikeLoadError(error) && attempt < ABORT_RETRY_LIMIT) {
          await sleep(ABORT_RETRY_DELAY_MS * (attempt + 1));
          return importWithRetry(attempt + 1);
        }

        if (isChunkLoadError(error) && attempt < CHUNK_RETRY_LIMIT) {
          await sleep(CHUNK_RETRY_DELAY_MS * (attempt + 1));
          return importWithRetry(attempt + 1);
        }

        if (tryRecoverChunkLoadError(error)) {
          await sleep(50);
        }
        throw error;
      }
    };

    return importWithRetry();
  });
};
