import React, { lazy, Suspense } from "react";

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
