import React, { useEffect, useState, ReactNode } from "react";
import HeaderComponent from "./components/HeaderComponent";
import FooterComponent from "./components/FooterComponent";

interface LayoutProps {
  children: ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [theme, setTheme] = useState<string>(
    localStorage.getItem("theme") || "light"
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  return (
    <div className="flex flex-col min-h-screen bg-footer-light text-dark-blue dark:bg-background-dark dark:text-text-light">
      <HeaderComponent toggleTheme={toggleTheme} currentTheme={theme} />
      <div className="relative flex-1 overflow-hidden">
        <div
          className={`absolute top-0 left-0 right-0 h-full w-full ${
            theme === "dark" ? "animate-dripDark" : "animate-drip"
          } bg-gradient-to-b from-primary-dark via-primary-mid to-footer-light dark:to-background-dark`}
        ></div>
        <div className="relative z-10 animate-fadeIn">{children}</div>
      </div>
      <FooterComponent />
    </div>
  );
};

export default Layout;
