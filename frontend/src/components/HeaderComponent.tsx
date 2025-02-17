import React, { lazy, Suspense } from "react";
import { useUserContext } from "../context/UserContext";
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
  const { isLoading } = useUserContext();

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
