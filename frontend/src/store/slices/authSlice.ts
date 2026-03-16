import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import { getCookie, removeCookie, clearAuthData } from "../../api";
import { log } from "../../api";

export interface UserProfile {
  id: number;
  username: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  date_joined?: string;
  last_login?: string;
  is_superuser?: boolean;
  is_staff?: boolean;
  phonenumber?: string;
  is_banned: boolean;
  last_login_ip?: string;
}

interface AuthState {
  user: UserProfile | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  accessTokenExpires: string | null;
  refreshTokenExpires: string | null;
}

const isTokenValid = (token: string | null): boolean => {
  if (!token) return false;

  try {
    const parts = token.split(".");
    if (parts.length !== 3) return false;

    const payload = JSON.parse(atob(parts[1]));

    if (payload.exp && payload.exp * 1000 < Date.now()) {
      return false;
    }

    return true;
  } catch (error) {
    log.error("Error validating token:", error);
    return false;
  }
};

const getInitialToken = (): string | null => {
  const accessToken = getCookie("access_token");
  const refreshToken = getCookie("refresh_token");
  if (accessToken && !isTokenValid(accessToken)) {
    if (refreshToken) {
      log.info(
        "Access token expired on init but refresh token present, keeping session"
      );
      return accessToken;
    }
    log.warn("Invalid access token and no refresh token, removing");
    removeCookie("access_token");
    return null;
  }
  return accessToken;
};

const getInitialUser = (): UserProfile | null => {
  try {
    const storedUser = localStorage.getItem("userProfile");
    if (storedUser) {
      return JSON.parse(storedUser);
    }
  } catch (error) {
    log.error("Error reading user from localStorage:", error);
    try {
      localStorage.removeItem("userProfile");
    } catch (innerError) {
      log.error("Failed to remove corrupted user data:", innerError);
    }
  }
  return null;
};

const getInitialAuth = () => {
  const token = getInitialToken();
  const user = getInitialUser();
  const hasRefresh = Boolean(getCookie("refresh_token"));
  return {
    user,
    token,
    isLoading: true,
    isAuthenticated: Boolean((token || hasRefresh) && user),
    accessTokenExpires: localStorage.getItem("access_token_expires"),
    refreshTokenExpires: localStorage.getItem("refresh_token_expires"),
  };
};

const initialState: AuthState = getInitialAuth();

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    setUser: (state, action: PayloadAction<UserProfile | null>) => {
      state.user = action.payload;
      state.isAuthenticated = Boolean(state.token && action.payload);

      if (action.payload) {
        try {
          localStorage.setItem("userProfile", JSON.stringify(action.payload));
        } catch (error) {
          log.error("Failed to save user to localStorage:", error);
        }
      } else {
        try {
          localStorage.removeItem("userProfile");
        } catch (error) {
          log.error("Failed to remove user from localStorage:", error);
        }
      }
    },
    setToken: (state, action: PayloadAction<string | null>) => {
      state.token = action.payload;
      state.isAuthenticated = Boolean(action.payload && state.user);
    },
    setTokens: (
      state,
      action: PayloadAction<{
        access: string;
        refresh?: string;
        accessTokenExpires?: string;
        refreshTokenExpires?: string;
      }>
    ) => {
      state.token = action.payload.access;
      state.isAuthenticated = Boolean(action.payload.access && state.user);

      if (action.payload.accessTokenExpires) {
        state.accessTokenExpires = action.payload.accessTokenExpires;
        try {
          localStorage.setItem(
            "access_token_expires",
            action.payload.accessTokenExpires
          );
        } catch (error) {
          log.error("Failed to save access token expiration:", error);
        }
      }

      if (action.payload.refreshTokenExpires) {
        state.refreshTokenExpires = action.payload.refreshTokenExpires;
        try {
          localStorage.setItem(
            "refresh_token_expires",
            action.payload.refreshTokenExpires
          );
        } catch (error) {
          log.error("Failed to save refresh token expiration:", error);
        }
      }
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload;
    },
    logout: (state) => {
      state.user = null;
      state.token = null;
      state.isAuthenticated = false;
      state.isLoading = false;
      state.accessTokenExpires = null;
      state.refreshTokenExpires = null;

      clearAuthData();
    },
    checkTokenExpiration: (state) => {
      try {
        const refreshTokenExpires = state.refreshTokenExpires;
        if (refreshTokenExpires) {
          const expiresDate = new Date(refreshTokenExpires);
          const now = new Date();

          if (expiresDate <= now) {
            log.warn("Refresh token expired, logging out");
            authSlice.caseReducers.logout(state);
          }
        }
      } catch (error) {
        log.error("Error checking token expiration:", error);
      }
    },
  },
});

export const {
  setUser,
  setToken,
  setTokens,
  setLoading,
  logout,
  checkTokenExpiration,
} = authSlice.actions;

export default authSlice.reducer;

