import React, { lazy, Suspense, useEffect } from "react";
import { useUserContext } from "../context/UserContext";
import { isAuthenticated } from "../utils/authHelpers";

type HeaderComponentProps = {
  toggleTheme: () => void;
  currentTheme: string;
};

const DesktopNavbar = lazy(() => import("./DesktopNavbar"));
const MobileNavbar = lazy(() => import("./MobileNavbar"));

const HeaderComponent: React.FC<HeaderComponentProps> = ({
  toggleTheme,
  currentTheme,
}) => {
  const { isLoading, user } = useUserContext();

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
