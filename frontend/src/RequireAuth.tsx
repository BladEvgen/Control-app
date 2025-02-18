import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { isAuthenticated } from "./utils/authHelpers";

const RequireAuth: React.FC = () => {
  const location = useLocation();

  if (!isAuthenticated()) {
    return <Navigate to="/app/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
};

export default RequireAuth;
