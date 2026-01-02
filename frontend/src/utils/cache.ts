export interface CacheEntry<T> {
  readonly data: T;
  readonly timestamp: number;
  readonly cacheDate: string; 
  readonly expiresAt: number; 
}

export type CacheKey = string;
export type CacheResult<T> = T | null;

const CACHE_PREFIX = "dept_cache_";

const getEndOfDayTimestamp = (date: Date = new Date()): number => {
  const endOfDay = new Date(date);
  endOfDay.setHours(23, 59, 59, 999);
  return endOfDay.getTime();
};

const getDateString = (date: Date = new Date()): string => {
  return date.toISOString().split("T")[0] as string;
};

const isCacheValidForToday = (cacheDate: string): boolean => {
  const today = getDateString();
  return cacheDate === today;
};

export const cacheManager = {
  set<T>(key: CacheKey, data: T): void {
    try {
      const now = Date.now();
      const today = getDateString();
      const expiresAt = getEndOfDayTimestamp();

      const entry: CacheEntry<T> = {
        data,
        timestamp: now,
        cacheDate: today,
        expiresAt,
      };

      const storageKey = `${CACHE_PREFIX}${key}`;
      localStorage.setItem(storageKey, JSON.stringify(entry));
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      console.warn("Failed to cache data:", errorMessage);
    }
  },

  get<T>(key: CacheKey): CacheResult<T> {
    try {
      const storageKey = `${CACHE_PREFIX}${key}`;
      const cached = localStorage.getItem(storageKey);

      if (!cached) {
        return null;
      }

      const entry: CacheEntry<T> = JSON.parse(cached);
      const now = Date.now();

      if (!isCacheValidForToday(entry.cacheDate) || now > entry.expiresAt) {
        localStorage.removeItem(storageKey);
        return null;
      }

      return entry.data;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      console.warn("Failed to read cache:", errorMessage);
      try {
        localStorage.removeItem(`${CACHE_PREFIX}${key}`);
      } catch (removeError) {
        void removeError;
      }
      return null;
    }
  },

  clear(key?: CacheKey): void {
    try {
      if (key) {
        const storageKey = `${CACHE_PREFIX}${key}`;
        localStorage.removeItem(storageKey);
      } else {
        const keysToRemove: string[] = [];
        for (let i = 0; i < localStorage.length; i++) {
          const storageKey = localStorage.key(i);
          if (storageKey && storageKey.startsWith(CACHE_PREFIX)) {
            keysToRemove.push(storageKey);
          }
        }
        keysToRemove.forEach((k) => localStorage.removeItem(k));
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      console.warn("Failed to clear cache:", errorMessage);
    }
  },

  isValid(key: CacheKey): boolean {
    try {
      const storageKey = `${CACHE_PREFIX}${key}`;
      const cached = localStorage.getItem(storageKey);

      if (!cached) {
        return false;
      }

      const entry: CacheEntry<unknown> = JSON.parse(cached);
      const now = Date.now();

      return (
        isCacheValidForToday(entry.cacheDate) && now <= entry.expiresAt
      );
    } catch {
      return false;
    }
  },

  invalidate(key: CacheKey): void {
    this.clear(key);
  },

  clearStale(): void {
    try {
      const keysToRemove: string[] = [];

      for (let i = 0; i < localStorage.length; i++) {
        const storageKey = localStorage.key(i);
        if (storageKey && storageKey.startsWith(CACHE_PREFIX)) {
          try {
            const cached = localStorage.getItem(storageKey);
            if (cached) {
              const entry: CacheEntry<unknown> = JSON.parse(cached);
              if (!isCacheValidForToday(entry.cacheDate)) {
                keysToRemove.push(storageKey);
              }
            }
          } catch {
            keysToRemove.push(storageKey);
          }
        }
      }

      keysToRemove.forEach((k) => localStorage.removeItem(k));
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      console.warn("Failed to clear stale cache:", errorMessage);
    }
  },
};

if (typeof window !== "undefined") {
  cacheManager.clearStale();

  window.addEventListener("userLoggedOut", () => {
    cacheManager.clear();
  });

  setInterval(() => {
    cacheManager.clearStale();
  }, 60 * 60 * 1000); 
}

