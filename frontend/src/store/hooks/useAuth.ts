import { useAppSelector, useAppDispatch } from "../hooks";
import {
  setUser,
  setToken,
  setTokens,
  setLoading,
  logout,
  checkTokenExpiration,
  UserProfile,
} from "../slices/authSlice";
import { useEffect } from "react";
import { getCookie, log } from "../../api";
import {
  clearRefreshSchedule,
  proactiveRefreshIfNeeded,
  scheduleNextRefreshBeforeExpiry,
} from "../../authSession/index.ts";
import { requestAppVersionCheck } from "../../utils/appVersionGuard";

const AUTH_SYNC_KEY = "app:authSync" as const;

const REFRESH_EXPIRY_TICK_MS = 30_000;

export const useAuth = () => {
  const dispatch = useAppDispatch();
  const user = useAppSelector((state) => state.auth.user);
  const token = useAppSelector((state) => state.auth.token);
  const isLoading = useAppSelector((state) => state.auth.isLoading);
  const isAuthenticated = useAppSelector((state) => state.auth.isAuthenticated);

  useEffect(() => {
    const currentToken = getCookie("access_token");
    if (currentToken !== token) {
      dispatch(setToken(currentToken));
    }
  }, [token, dispatch]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      dispatch(checkTokenExpiration());
      void proactiveRefreshIfNeeded();
    }, REFRESH_EXPIRY_TICK_MS);

    return () => window.clearInterval(interval);
  }, [dispatch]);

  useEffect(() => {
    if (token && getCookie("refresh_token")) {
      scheduleNextRefreshBeforeExpiry();
    } else if (!token) {
      clearRefreshSchedule();
    }
  }, [token]);

  useEffect(() => {
    const onUserLoggedIn = () => {
      const newToken = getCookie("access_token");
      dispatch(setToken(newToken));
      void requestAppVersionCheck("auth:userLoggedIn");
    };

    const onUserLoggedOut = () => {
      dispatch(logout());
    };

    const onTokensRefreshed = (event: Event) => {
      const customEvent = event as CustomEvent<{
        access: string;
        refresh?: string;
        accessTokenExpires?: string;
        refreshTokenExpires?: string;
      }>;
      if (customEvent.detail) {
        dispatch(setTokens(customEvent.detail));
        scheduleNextRefreshBeforeExpiry();
        void requestAppVersionCheck("auth:tokensRefreshed");
      }
    };

    const syncAuthFromOtherTab = () => {
      const access = getCookie("access_token");
      if (!access) return;
      const refresh = getCookie("refresh_token");
      const accessTokenExpires = localStorage.getItem("access_token_expires");
      const refreshTokenExpires = localStorage.getItem("refresh_token_expires");
      dispatch(
        setTokens({
          access,
          refresh: refresh ?? undefined,
          accessTokenExpires: accessTokenExpires ?? undefined,
          refreshTokenExpires: refreshTokenExpires ?? undefined,
        }),
      );
      scheduleNextRefreshBeforeExpiry();
      void requestAppVersionCheck("auth:syncFromOtherTab");
    };

    const onStorage = (e: StorageEvent) => {
      if (e.key === AUTH_SYNC_KEY && e.newValue) {
        syncAuthFromOtherTab();
      }
    };

    let channel: BroadcastChannel | null = null;
    if (typeof BroadcastChannel !== "undefined") {
      channel = new BroadcastChannel("auth");
      channel.onmessage = () => syncAuthFromOtherTab();
    }

    window.addEventListener("userLoggedIn", onUserLoggedIn);
    window.addEventListener("userLoggedOut", onUserLoggedOut);
    window.addEventListener("tokensRefreshed", onTokensRefreshed);
    window.addEventListener("storage", onStorage);

    return () => {
      window.removeEventListener("userLoggedIn", onUserLoggedIn);
      window.removeEventListener("userLoggedOut", onUserLoggedOut);
      window.removeEventListener("tokensRefreshed", onTokensRefreshed);
      window.removeEventListener("storage", onStorage);
      channel?.close();
    };
  }, [dispatch]);

  useEffect(() => {
    if (isLoading) {
      const loadingTimeout = setTimeout(() => {
        log.warn("Loading timeout reached, forcing loading state to complete");
        dispatch(setLoading(false));
      }, 5000);

      return () => clearTimeout(loadingTimeout);
    }
  }, [isLoading, dispatch]);

  useEffect(() => {
    if (token && !user) {
      const storedUser = localStorage.getItem("userProfile");
      if (storedUser) {
        try {
          const parsedUser = JSON.parse(storedUser);
          dispatch(setUser(parsedUser));
        } catch (error) {
          log.error("Error parsing stored user:", error);
        }
      }
      dispatch(setLoading(false));
    } else if (token && user) {
      dispatch(setLoading(false));
    } else if (!token) {
      dispatch(setLoading(false));
    }
  }, [token, user, dispatch]);

  return {
    user,
    setUser: (user: UserProfile | null) => dispatch(setUser(user)),
    token,
    isLoading,
    isAuthenticated,
    logout: () => dispatch(logout()),
    setTokens: (tokens: {
      access: string;
      refresh?: string;
      accessTokenExpires?: string;
      refreshTokenExpires?: string;
    }) => dispatch(setTokens(tokens)),
    setLoading: (loading: boolean) => dispatch(setLoading(loading)),
  };
};
