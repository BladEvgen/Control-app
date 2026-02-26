import React, { Suspense, useEffect } from "react";
import { useAuth } from "../store/hooks";
import { isAuthenticated } from "../utils/authHelpers";
import { lazyWithRetry } from "../utils/lazyWithRetry";

type HeaderComponentProps = {
  toggleTheme: () => void;
  currentTheme: string;
};

const DesktopNavbar = lazyWithRetry(() => import("./DesktopNavbar"));
const MobileNavbar = lazyWithRetry(() => import("./MobileNavbar"));

const HeaderComponent: React.FC<HeaderComponentProps> = ({
  toggleTheme,
  currentTheme,
}) => {
  const { isLoading, user } = useAuth();

  useEffect(() => {
    const authStatus = isAuthenticated();

    if (!authStatus && user) {
      window.dispatchEvent(new Event("userLoggedOut"));
    }
  }, [user]);

  if (isLoading) {
    return <header></header>;
  }

  return (
    <header className="bg-primary-dark text-text-light shadow-md">
      <Suspense fallback={null}>
        <div className="hidden lg:block">
          <DesktopNavbar
            toggleTheme={toggleTheme}
            currentTheme={currentTheme}
          />
        </div>
        <div className="lg:hidden">
          <MobileNavbar toggleTheme={toggleTheme} currentTheme={currentTheme} />
        </div>
      </Suspense>
    </header>
  );
};

export default HeaderComponent;
