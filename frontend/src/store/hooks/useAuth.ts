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
import { getCookie } from "../../api";
import { log } from "../../api";

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
    const interval = setInterval(() => {
      dispatch(checkTokenExpiration());
    }, 60000);

    return () => clearInterval(interval);
  }, [dispatch]);

  useEffect(() => {
    const onUserLoggedIn = () => {
      const newToken = getCookie("access_token");
      dispatch(setToken(newToken));
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
      }
    };

    window.addEventListener("userLoggedIn", onUserLoggedIn);
    window.addEventListener("userLoggedOut", onUserLoggedOut);
    window.addEventListener("tokensRefreshed", onTokensRefreshed);

    return () => {
      window.removeEventListener("userLoggedIn", onUserLoggedIn);
      window.removeEventListener("userLoggedOut", onUserLoggedOut);
      window.removeEventListener("tokensRefreshed", onTokensRefreshed);
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
  };
};

