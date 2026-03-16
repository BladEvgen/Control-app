import React, { useEffect } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { isAuthenticated } from "./utils/authHelpers";
import { useAuth } from "./store/hooks";
import { addPrefix } from "./RouterUtils";

const RequireAuth: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { isLoading } = useAuth();

  useEffect(() => {
    let authCheckTimer: number | null = null;

    if (!location.pathname.includes("/login")) {
      authCheckTimer = window.setTimeout(() => {
        if (!isAuthenticated()) {
          console.warn("Authentication check timed out - redirecting to login");
          navigate(addPrefix("/login"), {
            state: { from: location },
            replace: true,
          });
        }
      }, 8000);
    }

    return () => {
      if (authCheckTimer) {
        window.clearTimeout(authCheckTimer);
      }
    };
  }, [location.pathname, location, navigate]);

  if (isLoading) {
    return null;
  }
  if (!isAuthenticated()) {
    return (
      <Navigate to={addPrefix("/login")} state={{ from: location }} replace />
    );
  }

  return <Outlet />;
};

export default RequireAuth;
