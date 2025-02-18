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
import { getCookie } from "../api";
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
    localStorage.setItem("userProfile", JSON.stringify(user));
  } else {
    localStorage.removeItem("userProfile");
  }
};

export const UserProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [isLoading, setIsLoading] = useState(true);
  const storedUser = localStorage.getItem("userProfile");
  const [user, setUser] = useState<UserProfile | null>(
    storedUser ? JSON.parse(storedUser) : null
  );

  const updateUser = useCallback((value: UserProfile | null | ((prev: UserProfile | null) => UserProfile | null)) => {
    setUser(value);
    if (typeof value !== 'function') {
      saveUserToStorage(value);
    }
  }, []);

  const [token, setToken] = useState<string | null>(getCookie("access_token"));

  useEffect(() => {
    const fetchUserData = async () => {
      if (token && !user) {
        try {
          const response = await axiosInstance.get("/user/profile/");
          updateUser(response.data);
        } catch (error) {
          console.error("Error fetching user data:", error);
          updateUser(null);
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
