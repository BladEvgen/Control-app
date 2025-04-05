import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import { apiUrl } from "../../apiConfig";
import useWebSocket from "../hooks/useWebSocket";
import { log } from "../api";
import { getCookie, clearAuthData, removeCookie } from "../api";
import axiosInstance from "../api";

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

interface UserContextType {
  user: UserProfile | null;
  setUser: React.Dispatch<React.SetStateAction<UserProfile | null>>;
  isLoading: boolean;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

const saveUserToStorage = (user: UserProfile | null) => {
  if (user) {
    try {
      localStorage.setItem("userProfile", JSON.stringify(user));
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
};

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

export const UserProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadingTimeout = setTimeout(() => {
      if (isLoading) {
        log.warn("Loading timeout reached, forcing loading state to complete");
        setIsLoading(false);
      }
    }, 5000);

    return () => clearTimeout(loadingTimeout);
  }, [isLoading]);

  let initialUser: UserProfile | null = null;
  try {
    const storedUser = localStorage.getItem("userProfile");
    if (storedUser) {
      initialUser = JSON.parse(storedUser);
    }
  } catch (error) {
    log.error("Error reading user from localStorage:", error);
    try {
      localStorage.removeItem("userProfile");
    } catch (innerError) {
      log.error("Failed to remove corrupted user data:", innerError);
    }
  }

  const [user, setUser] = useState<UserProfile | null>(initialUser);

  const updateUser = useCallback(
    (
      value:
        | UserProfile
        | null
        | ((prev: UserProfile | null) => UserProfile | null)
    ) => {
      setUser(value);
      if (typeof value !== "function") {
        saveUserToStorage(value);
      }
    },
    []
  );

  const [token, setToken] = useState<string | null>(() => {
    const accessToken = getCookie("access_token");
    if (accessToken && !isTokenValid(accessToken)) {
      log.warn("Invalid access token detected on initialization, removing");
      removeCookie("access_token");
      return null;
    }
    return accessToken;
  });

  useEffect(() => {
    const fetchUserData = async () => {
      if (token && !user) {
        try {
          const response = await axiosInstance.get("/user/profile/");
          updateUser(response.data);
        } catch (error) {
          console.error("Error fetching user data:", error);
          updateUser(null);

          if (
            error &&
            typeof error === "object" &&
            "response" in error &&
            error.response &&
            typeof error.response === "object" &&
            "status" in error.response &&
            (error.response.status === 401 || error.response.status === 403)
          ) {
            log.warn("Authentication error, clearing auth data");
            clearAuthData();
            setToken(null);
          }
        } finally {
          setIsLoading(false);
        }
      } else {
        setIsLoading(false);
      }
    };

    fetchUserData();
  }, [token, user, updateUser]);

  useEffect(() => {
    const onUserLoggedIn = () => {
      const newToken = getCookie("access_token");
      setToken(newToken);
    };
    window.addEventListener("userLoggedIn", onUserLoggedIn);
    return () => {
      window.removeEventListener("userLoggedIn", onUserLoggedIn);
    };
  }, []);

  useEffect(() => {
    const onUserLoggedOut = () => {
      updateUser(null);
      setToken(null);
    };
    window.addEventListener("userLoggedOut", onUserLoggedOut);
    return () => window.removeEventListener("userLoggedOut", onUserLoggedOut);
  }, [updateUser]);

  useEffect(() => {
    const checkTokenExpiration = () => {
      try {
        const refreshTokenExpires = localStorage.getItem(
          "refresh_token_expires"
        );
        if (refreshTokenExpires) {
          const expiresDate = new Date(refreshTokenExpires);
          const now = new Date();

          if (expiresDate <= now) {
            log.warn("Refresh token expired, logging out");
            window.dispatchEvent(new Event("userLoggedOut"));
            return;
          }

          const timeout = expiresDate.getTime() - now.getTime();
          const checkInterval = Math.min(timeout, 3600000);

          const timerId = setTimeout(checkTokenExpiration, checkInterval);
          return () => clearTimeout(timerId);
        }
      } catch (error) {
        log.error("Error checking token expiration:", error);
      }
    };

    checkTokenExpiration();
  }, [token]);

  const wsUrl = useMemo(() => {
    if (!token) return null;
    const urlObj = new URL(apiUrl);
    const protocol = urlObj.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${urlObj.host}/ws/user-detail/?token=${token}`;
  }, [token, apiUrl]);

  const { sendMessage } = useWebSocket({
    url: wsUrl || "",
    onMessage: (event) => {
      try {
        const data = JSON.parse(event.data);
        log.info("UserContext received:", data);
        if (data.error) {
          console.error("Error getting profile:", data.error);
        } else if (data.user) {
          updateUser(data.user);
        } else {
          updateUser(data);
        }
      } catch (error) {
        console.error("Error parsing WS message:", error);
      }
    },
    onOpen: () => {
      if (wsUrl) {
        sendMessage(JSON.stringify({ action: "get_profile" }));
      }
    },
  });

  const contextValue = useMemo(
    () => ({
      user,
      setUser: updateUser,
      isLoading,
    }),
    [user, updateUser, isLoading]
  );

  return (
    <UserContext.Provider value={contextValue}>{children}</UserContext.Provider>
  );
};

export const useUserContext = () => {
  const context = useContext(UserContext);
  if (!context) {
    throw new Error("useUserContext must be used within a UserProvider");
  }
  return context;
};
