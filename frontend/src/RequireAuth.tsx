import React, { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { isAuthenticated } from "./utils/authHelpers";
import { useUserContext } from "./context/UserContext";

const RequireAuth: React.FC = () => {
  const location = useLocation();
  const { isLoading } = useUserContext();

  useEffect(() => {
    let authCheckTimer: number | null = null;

    if (!location.pathname.includes("/login")) {
      authCheckTimer = window.setTimeout(() => {
        if (!isAuthenticated()) {
          console.warn("Authentication check timed out - redirecting to login");
          window.location.href = "/app/login";
        }
      }, 8000);
    }

    return () => {
      if (authCheckTimer) {
        window.clearTimeout(authCheckTimer);
      }
    };
  }, [location.pathname]);

  if (isLoading) {
    return null;
  }
  if (!isAuthenticated()) {
    return <Navigate to="/app/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
};

export default RequireAuth;
