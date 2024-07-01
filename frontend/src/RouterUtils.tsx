import {
  Link as RouterLink,
  useNavigate as useRouterNavigate,
} from "react-router-dom";
import React, { ReactNode } from "react";

export const addPrefix = (path: string) => `/app${path}`;

interface CustomLinkProps {
  to: string | number;
  children: ReactNode;
  [key: string]: any;
}

export const Link: React.FC<CustomLinkProps> = ({ to, children, ...props }) => {
  const prefixedTo = typeof to === "string" ? addPrefix(to) : `/app/${to}`;
  return (
    <RouterLink to={prefixedTo} {...props}>
      {children}
    </RouterLink>
  );
};

export const useNavigate = () => {
  const navigate = useRouterNavigate();
  return (
    to: string | number,
    options?: { replace?: boolean; state?: any }
  ) => {
    const prefixedTo = typeof to === "string" ? addPrefix(to) : `/app/${to}`;
    navigate(prefixedTo, options);
  };
};
